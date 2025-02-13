# agent.py
from typing import Dict, List, TypedDict, Any, Annotated
from operator import add
import operator
from langgraph.graph import StateGraph, START, END
from cosmos_db import CosmosDBManager
from pydantic import BaseModel
from langgraph.constants import Send
import os
import json
from azure.communication.email import EmailClient
# NEW IMPORTS for LLM
from langchain_openai import AzureChatOpenAI

from langsmith import traceable
from databricks import sql
import os

# Initialize empty strings for skills and competencies

# Enable/disable email notifications
ENABLE_EMAIL_NOTIFICATIONS = True

# Initialize CosmosDB
cosmos_db = CosmosDBManager()

# Initialize the LLM using environment variables (ensure these are set)
llm = AzureChatOpenAI(
    azure_deployment=os.getenv("AOAI_DEPLOYMENT"),
    api_version="2024-05-01-preview",
    temperature=0,
    max_tokens=1500,   # Adjust as needed
    timeout=10,
    max_retries=2,
    api_key=os.getenv("AOAI_KEY"),
    azure_endpoint=os.getenv("AOAI_ENDPOINT")
)

#Azure Communication Services
email_client = EmailClient.from_connection_string(os.environ.get("COMMUNICATION_SERVICES_CONNECTION_STRING"))
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")

# -------------------------------
# Type definitions for employee subgraph
# -------------------------------
class EmployeeState(TypedDict):
    """State for an individual employee analysis"""
    employee_id: str
    workday_data: Dict[str, Any]
    project_history: List[Dict[str, Any]]
    approved_values: Dict[str, Any]
    skills_analysis: str | None
    project_analysis: str | None
    combined_analysis: List[str]

class EmployeeOutputState(TypedDict):
    """Output state from employee subgraph"""
    combined_analysis: List[str]

# -------------------------------
# Type definitions for main graph
# -------------------------------
class MainState(TypedDict):
    """Main state for the workflow"""
    employee_ids: List[str]
    approved_values: Dict[str, Any]
    workday_data: List[Dict[str, Any]]
    project_history: List[List[Dict[str, Any]]]
    combined_analysis: Annotated[List[str], operator.add]
    final_report: str | None
    

# -------------------------------
# Main Graph Functions
# -------------------------------
@traceable(run_type="tool", name="Databricks Query")
def get_target_employees(state: MainState) -> MainState:
    """
    Get employees with fewer than 7 approved skills.
    (You may adjust this query as needed.)
    """
    query = """
    SELECT c.id, c.employee_id, c.partitionKey, c.name, c.type, c.approved_skills, c.competencies, c.free_text_skills, c.certifications
    FROM c 
    WHERE c.partitionKey = 'employee' 
      AND ARRAY_LENGTH(c.approved_skills) < 7
    """
    employees = list(cosmos_db.query_items(query))
    
    # Removed 'target_employees'; now capturing employees solely via employee_ids.
    state["employee_ids"] = [emp.get("employee_id") for emp in employees]
    
    print(f"\nFound {len(employees)} employees with fewer than 7 approved skills")
    return state

@traceable(run_type="tool", name="Databricks Query")
def get_company_approved_values(state: MainState) -> MainState:
    """
    Retrieve the company approved values (skills and competencies) from Databricks.
    Assumes that the table 'hive_metastore.default.approved_values' contains columns 
    'approved_skill' and 'approved_competency'.
    """
    approved_skills = []
    approved_competencies = []
    
    try:
        with sql.connect(
            server_hostname=os.getenv("DATABRICKS_SERVER_HOSTNAME"),
            http_path=os.getenv("DATABRICKS_HTTP_PATH"),
            access_token=os.getenv("DATABRICKS_TOKEN")
        ) as connection:
            with connection.cursor() as cursor:
                # Adjust the SELECT clause as needed (here we explicitly select the two columns)
                cursor.execute("SELECT approved_skill, approved_competency FROM hive_metastore.default.approved_values")
                results = cursor.fetchall()
                
                for row in results:
                    # Depending on your row type, you might need to access the columns by index (row[0], row[1])
                    # or by attribute (row.approved_skill, row.approved_competency). Adjust accordingly.
                    approved_skills.append(row.approved_skill)
                    approved_competencies.append(row.approved_competency)
        
        state["approved_values"] = {
            "approved_skills": approved_skills,
            "approved_competencies": approved_competencies
        }
        print("Retrieved company approved values from Databricks.")
        
    except Exception as e:
        print(f"Error retrieving company approved values from Databricks: {e}")
        state["approved_values"] = {}
    
    return state


@traceable(run_type="tool", name="Databricks Query")
def get_employee_data(state: MainState) -> MainState:
    """
    For each employee (via employee_ids), retrieve their workday data and project history.
    """
    workday_data_list = []
    project_history_list = []
    
    for emp_id in state["employee_ids"]:
        # Query for workday data (only the necessary fields)
        workday_query = f"""
        SELECT c.id, c.employee_id, c.partitionKey, c.name, c.type, c.approved_skills, c.competencies, c.free_text_skills, c.certifications
        FROM c 
        WHERE c.partitionKey = 'employee'
          AND c.employee_id = '{emp_id}'
        """
        workday_results = list(cosmos_db.query_items(workday_query))
        
        # Query for project history (only necessary fields)
        project_query = f"""
        SELECT c.id, c.employee_id, c.partitionKey, c.name, c.type, c.projects
        FROM c 
        WHERE c.partitionKey = 'project_history'
          AND c.employee_id = '{emp_id}'
        """
        project_results = list(cosmos_db.query_items(project_query))
        
        if workday_results:
            workday_record = workday_results[0]
            workday_data_list.append(workday_record)
            
            projects = project_results[0].get("projects", []) if project_results else []
            project_history_list.append(projects)
            
            print(f"Retrieved complete data for employee {emp_id}")
        else:
            print(f"Warning: Incomplete data for employee {emp_id}")
    
    state["workday_data"] = workday_data_list
    state["project_history"] = project_history_list
    
    print(f"\nRetrieved data for {len(workday_data_list)} employees")
    return state

def distribute_employees(state: MainState) -> List[Send]:
    """
    Distribute each employee's data (workday and project history) to a separate subgraph instance.
    We assume that the order of workday_data and project_history lists align with employee_ids.
    """
    sends = []
    for i, workday in enumerate(state["workday_data"]):
        project_hist = state["project_history"][i] if i < len(state["project_history"]) else []
        sends.append(Send("employee_processor", {
            "employee_id": workday.get("employee_id"),
            "workday_data": workday,
            "project_history": project_hist,
            "approved_values": state.get("approved_values", {}),
            "skills_analysis": None,
            "project_analysis": None,
            "combined_analysis": []
        }))
    return sends

def finalize(state: MainState) -> MainState:
    """
    In this simplified main graph, we assume that employee analyses have been
    collected (e.g. from each subgraph) and we leave state as is.
    """
    # Optionally, you could join the analyses here.
    return state

# -------------------------------
# Employee Subgraph Functions
# -------------------------------
def analyze_skills(state: EmployeeState) -> EmployeeState:
    """Analyze employee skills and competencies"""
    print(f"\n{'='*50}")
    print(f"Analyzing Skills for Employee: {state['employee_id']}")
    
    workday_data = state['workday_data']
    skills = workday_data.get('approved_skills', [])
    competencies = workday_data.get('competencies', {})
    free_text = workday_data.get('free_text_skills', [])
    certifications = workday_data.get('certifications', [])
    
    # Build preliminary analysis log for display
    analysis_log = f"""
    Skills Analysis for {workday_data.get('name')}:
    ------------------------------------------
    Approved Skills ({len(skills)}): {', '.join(skills)}
    
    Competencies:
    {chr(10).join(f'- {comp}: {level}' for comp, level in competencies.items())}
    
    Additional Skills:
    {chr(10).join(f'- {skill}' for skill in free_text)}
    
    Certifications:
    {chr(10).join(f'- {cert}' for cert in certifications)}
    """
    print(analysis_log)
    print(f"{'='*50}")
    
    # Retrieve company approved values for inclusion in the prompt
    approved_values = state.get("approved_values", {})
    approved_skills = approved_values.get("approved_skills", [])
    approved_competencies = approved_values.get("approved_competencies", [])
    
    workday_data_prompt = """You are a skills updater agent specializing in making sure an employee's skills and competencies are aligned with company standards and up to date. You will be provided an employee's 
    current approved skills, certifications, competencies, and their free-text skills/competencies. You will also be provided the company-approved list of approved skills and competencies. Please do the following:

    1. Look at the employee's existing approved skills, certifications, competencies, and their free-text skills/competencies 
    2. Compare their free-text skills/competencies to the company's approved skills and competencies and determine which approved skills/competencies are missing and should be added to their profile. 
    3. Look at the certifications and competencies. Can we glean any approved skills from these? 
    4. Look at the approved skills and certifications. Can we glean any approved competencies from these? 

    Our goal is to closely analyze all of the available information and come up with a list of the company-approved skills and competencies that the employee should have on their profile. 

    Output Format:

    1. thought_process: Analyze the employees current skills, certifications, and competencies. Cross-reference with the company-approved values. What do you see? What can we glean? What is missing? We should look for obvious mappings between free-text skills and the approved values, but also less obvious ones that need to be gleaned from certifications or other values.
    2. new_skills: List the company-approved skills that the employee does not have (formalized version of your thought process, list them here)
    3. new_competencies: List the company-approved competencies that the employee does not have (formalized version of your thought process, list them here)

    For each skill and competency, include a % confidence value. For obvious matches with the approved skills, put 100%. For less obvious matches, put some % but be careful not to overstate the confidence.

    """
    
    llm_input = f"""### Employee Name: {workday_data.get('name')} ###
Existing Approved Skills: {', '.join(skills)}
Free Text Skills: {', '.join(free_text)}
Existing Approved Competencies:
{chr(10).join(f"- {comp}: {level}" for comp, level in competencies.items())}
Existing Certifications: {', '.join(certifications)}

### Company Approved Values ###
<Approved Skills>
 {', '.join(approved_skills)}
</Approved Skills>
<Approved Competencies> 
{', '.join(approved_competencies)}
</Approved Competencies>


"""
    messages = [
        {"role": "system", "content": workday_data_prompt},
        {"role": "user", "content": llm_input}
    ]
    response = llm.invoke(messages)
    skills_analysis = response.content.strip()  # Assuming the LLM returns a .content attribute
    state['skills_analysis'] = skills_analysis
    
    print("\nLLM Skills Analysis:")
    print(skills_analysis)
    
    return state



def analyze_project_history(state: EmployeeState) -> EmployeeState:
    """Analyze employee project history"""
    print(f"\n{'='*50}")
    print(f"Analyzing Project History for Employee: {state['employee_id']}")
    print(f"{'='*50}")

    project_history = state.get('project_history', [])
    # Convert each project history record to a formatted JSON string.
    project_history_str = "\n".join(json.dumps(record, indent=2) for record in project_history)
    print("Project History:")
    print(project_history_str)
    
    # Retrieve company approved values for inclusion in the prompt
    approved_values = state.get("approved_values", {})
    approved_skills = approved_values.get("approved_skills", [])
    approved_competencies = approved_values.get("approved_competencies", [])

    # Retrieve workday_data details (skills, competencies, certifications)
    workday_data = state.get("workday_data", {})
    employee_name = workday_data.get('name', 'Unknown Employee')
    skills = workday_data.get('approved_skills', [])
    competencies = workday_data.get('competencies', {})
    certifications = workday_data.get('certifications', [])

    # Build the LLM input with the additional workday_data information
    llm_input = f"""Employee Name: {employee_name}

Existing Approved Skills: {', '.join(skills)}
Existing Competencies:
{chr(10).join(f"- {comp}: {level}" for comp, level in competencies.items())}
Existing Certifications: {', '.join(certifications)}

Project History:
{project_history_str}

### Company Approved Values ###
<Approved Skills>
 {', '.join(approved_skills)}
</Approved Skills>
<Approved Competencies> 
{', '.join(approved_competencies)}
</Approved Competencies>
"""

    project_history_prompt = """You are a skills updater agent specializing in making sure an employee's skills and competencies are aligned with company standards and up to date. You will be provided an employee's 
project history along with their existing approved skills, competencies, and certifications. You will also be provided the company-approved list of approved skills and competencies. Please do the following:

1. Review the employee's project history in the context of their current profile (skills, competencies, and certifications).
2. Identify which company-approved skills and competencies might be missing from the employee's profile based on both their historical projects and the existing profile details.

Our goal is to closely analyze all available information and produce a list of company-approved skills and competencies that the employee should have on their profile.

Output Format:

1. thought_process: A detailed analysis of the employee's profile and project history, highlighting any discrepancies or missing items.
2. new_skills: A list of the company-approved skills that the employee is missing. 
3. new_competencies: A list of the company-approved competencies that the employee is missing.

For each skill and competency, include a % confidence value. For obvious matches with the approved skills, put 100%. For less obvious matches, put some % but be careful not to overstate the confidence.

"""

    messages = [
        {"role": "system", "content": project_history_prompt},
        {"role": "user", "content": llm_input}
    ]
    response = llm.invoke(messages)
    project_analysis = response.content.strip()
    state['project_analysis'] = project_analysis

    print("\nLLM Project Analysis:")
    print(project_analysis)
    
    return state



def review_and_combine(state: EmployeeState) -> EmployeeState:
    """Combine skills and project analyses into final employee analysis using an additional LLM call for consolidation."""
    print(f"\n{'='*50}")
    print(f"Combining Analyses for Employee: {state['employee_id']}")
    print(f"{'='*50}")
    
    employee_name = state['workday_data'].get('name', 'Unknown Employee')
    
    # Build the system prompt that instructs the LLM for consolidation.
    consolidation_prompt = """You are an advanced skills aggregator agent. Your task is to consolidate two separate analyses into one unified summary. Please follow these instructions:

1. Provide a detailed thought_process explaining how both the employee data & project history were used to infer skills/competencies. 
2. Produce a new_skills list with recommended company-approved skills, each with a % confidence value. 
3. Produce a new_competencies list with recommended company-approved competencies, each with a % confidence value. 

Your response should be clearly formatted with the following sections:
- thought_process
- new_skills
- new_competencies

###Guidance###

Do not include any additional text beyond these sections.
If you see a recommended skill as 100% confidence in one of the data sources and 50% in the other, you should not necessarily average the confidence. We want to use both data points to determine the final confidence %. If our skills analysis was 100% confident, then we can assume we had enough data in that analysis to be 100% confident overall. 
"""
    
    # Build the llm_input variable that includes the employee's data and both analyses.
    llm_input = f"""Employee Name: {employee_name}

### Analysis from Workday Data (Skills Assessment):
{state['skills_analysis']}

### Analysis from Project History:
{state['project_analysis']}
"""
    
    messages = [
        {"role": "system", "content": consolidation_prompt},
        {"role": "user", "content": llm_input}
    ]
    
    # Invoke the LLM to get the consolidated analysis.
    response = llm.invoke(messages)
    consolidated_output = response.content.strip()
    
    # Build the final combined analysis by including the employee name and the consolidated output.
    final_combined_analysis = f"""
Complete Analysis for {employee_name}
{'='*50}

Final Analysis:
{consolidated_output}

{'='*50}
"""
    
    # Save the final output into the state (as a list of strings)
    state['combined_analysis'] = [final_combined_analysis]
    
    print("\nFinal Analysis:")
    print(final_combined_analysis)
    
    return state



def send_notification(state: EmployeeState) -> EmployeeState:
    """Send an email notification to the employee with their skills and competencies analysis."""
    print(f"\n{'='*50}")
    print(f"Processing notification for Employee: {state['employee_id']}")
    print(f"{'='*50}")

    if not ENABLE_EMAIL_NOTIFICATIONS:
        print("Email notifications are disabled. Skipping email send.")
        return state

    # Get the employee's name and combined analysis text
    employee_name = state['workday_data'].get('name', 'Employee')
    # Join the analysis results (assumed to be a list of strings)
    combined_analysis_text = "\n\n".join(state.get('combined_analysis', []))

    # Build the email subject and body
    subject = f"Skills & Competencies Update Recommendation for {employee_name}"
    
    html_content = f"""
    <html>
        <head>
            <style>
                body {{
                    font-family: Arial, sans-serif;
                    line-height: 1.6;
                    padding: 20px;
                    background-color: #f4f4f4;
                }}
                .container {{
                    max-width: 600px;
                    margin: auto;
                    background: #ffffff;
                    padding: 20px;
                    border-radius: 8px;
                    box-shadow: 0 2px 4px rgba(0, 0, 0, 0.1);
                }}
                h1 {{
                    font-size: 24px;
                    color: #333333;
                }}
                pre {{
                    background: #f4f4f4;
                    padding: 10px;
                    border-radius: 4px;
                    overflow-x: auto;
                }}
                .recommendations-link {{
                    color: #0066cc;
                    text-decoration: none;
                    margin-bottom: 15px;
                    display: inline-block;
                }}
                .recommendations-link:hover {{
                    text-decoration: underline;
                }}
            </style>
        </head>
        <body>
            <div class="container">
                <h1>Skills &amp; Competencies Update Recommendation</h1>
                <a href="http://localhost:3000/recommendations" class="recommendations-link">View and Validate Recommendations</a>
                <p>Hello {employee_name},</p>
                <p>Please review the analysis below regarding your current skills and competencies:</p>
                <pre>{combined_analysis_text}</pre>
                <p>Best regards,<br/>HR Team</p>
            </div>
        </body>
    </html>
    """

    # Build the email message
    email_message = {
        "senderAddress": SENDER_EMAIL,
        "recipients": {
            "to": [{"address": RECIPIENT_EMAIL}]
        },
        "content": {
            "subject": subject,
            "plainText": combined_analysis_text,
            "html": html_content
        }
    }

    # Send the email using the email_client
    try:
        poller = email_client.begin_send(email_message)
        result = poller.result()
        print(f"Notification sent successfully to {RECIPIENT_EMAIL}")
    except Exception as e:
        print(f"Failed to send email: {e}")

    return state


# -------------------------------
# Build employee subgraph
# -------------------------------
builder = StateGraph(EmployeeState, output=EmployeeOutputState)
builder.add_node("analyze_skills", analyze_skills)
builder.add_node("analyze_project_history", analyze_project_history)
builder.add_node("review_and_combine", review_and_combine)
builder.add_node("send_notification", send_notification)

builder.add_edge(START, "analyze_skills")
builder.add_edge("analyze_skills", "analyze_project_history")
builder.add_edge("analyze_project_history", "review_and_combine")
builder.add_edge("review_and_combine", "send_notification")
builder.add_edge("send_notification", END)

employee_processor = builder.compile()

# -------------------------------
# Build Main Graph
# -------------------------------
main_graph_builder = StateGraph(MainState)
main_graph_builder.add_node("get_target_employees", get_target_employees)
main_graph_builder.add_node("get_company_approved_values", get_company_approved_values)
main_graph_builder.add_node("get_employee_data", get_employee_data)
main_graph_builder.add_node("employee_processor", employee_processor)
main_graph_builder.add_node("finalize", finalize)

main_graph_builder.add_edge(START, "get_target_employees")
main_graph_builder.add_edge("get_target_employees", "get_company_approved_values")
main_graph_builder.add_edge("get_company_approved_values", "get_employee_data")
main_graph_builder.add_conditional_edges(
    "get_employee_data",
    distribute_employees,
    ["employee_processor"]
)
main_graph_builder.add_edge("employee_processor", "finalize")
main_graph_builder.add_edge("finalize", END)

graph = main_graph_builder.compile()

# --------------------------------------
# Main Execution
# --------------------------------------
def main():
    """Run the employee analysis workflow."""
    print("\n=== Employee Skills Analysis System ===")
    initial_state = MainState(
        employee_ids=[],
        approved_values={},
        workday_data=[],
        project_history=[],
        combined_analysis=[],
        final_report=None
    )
    final_state = graph.invoke(initial_state)
    

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {str(e)}")
