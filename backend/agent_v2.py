#Competencies Agent
from typing import Dict, List, Any, Optional
import os
import pandas as pd
from datetime import datetime
from azure.communication.email import EmailClient
from langchain_openai import AzureChatOpenAI
from pydantic import BaseModel
from cosmos_db import CosmosDBManager  # Import the CosmosDBManager

# Enable/disable email notifications
ENABLE_EMAIL_NOTIFICATIONS = False

# Cosmos DB configuration
COSMOS_DATABASE_ID = "test_db"
COSMOS_CONTAINER_ID = "people"


class CompetencyRecommendation(BaseModel):
    """Represents a single competency recommendation with confidence, level, and reasoning"""
    competency: str
    level: str  # One of: "beginner", "intermediate", "advanced", "expert"
    confidence: int  # Percentage confidence (0-100)
    reasoning: str


class CompetencyAnalysis(BaseModel):
    """Complete analysis output from the LLM"""
    thought_process: str
    new_competencies: List[CompetencyRecommendation]


class EmployeeCompetencyRecord(BaseModel):
    """Record to be stored in Cosmos DB for each employee analysis"""
    id: str  # employee_id for the document ID
    partitionKey: str  # Using employee_id for the partition key as well
    employee_id: str
    employee_name: str
    employee_email: str
    analysis_result: CompetencyAnalysis
    notification_sent: bool = False
    notification_timestamp: Optional[str] = None
    approved: bool = False
    approved_timestamp: Optional[str] = None


# Initialize the LLM using environment variables (ensure these are set)
llm = AzureChatOpenAI(
    azure_deployment=os.getenv("AOAI_DEPLOYMENT"),
    api_version="2024-05-01-preview",
    temperature=0,
    max_tokens=1500,   # Adjust as needed
    timeout=None,
    max_retries=2,
    api_key=os.getenv("AOAI_KEY"),
    azure_endpoint=os.getenv("AOAI_ENDPOINT")
)

# Azure Communication Services
email_client = EmailClient.from_connection_string(os.environ.get("COMMUNICATION_SERVICES_CONNECTION_STRING"))
SENDER_EMAIL = os.getenv("SENDER_EMAIL")

# CSV File Paths
EMPLOYEES_WORKDAY_CSV = "D:/data/dxc/employee_data_workday.csv"
PSE_DATA_CSV = "D:/data/dxc/employee_data_pse.csv"
APPROVED_VALUES_CSV = "D:/data/dxc/approved_values.csv"

# -------------------------------
# CSV Helper Functions
# -------------------------------
def read_employees_csv(file_path=EMPLOYEES_WORKDAY_CSV):
    """Read employee data from CSV file"""
    try:
        df = pd.read_csv(file_path)
        
        # Process the DataFrame to handle complex columns
        employees = []
        for _, row in df.iterrows():
            # Convert competencies string to dictionary (assuming format like "skill1:level1,skill2:level2")
            competencies = {}
            if pd.notna(row.get('competencies')):
                for comp in row['competencies'].split(','):
                    if ':' in comp:
                        skill, level = comp.split(':', 1)
                        competencies[skill.strip()] = level.strip()
            
            # Convert certifications and cloud_skills to lists
            certifications = []
            if pd.notna(row.get('certifications')):
                certifications = [cert.strip() for cert in row['certifications'].split(',')]
                
            cloud_skills = []
            if pd.notna(row.get('cloud_skills')):
                cloud_skills = [skill.strip() for skill in row['cloud_skills'].split(',')]
            
            employee = {
                'employee_id': row['employee_id'],
                'name': row['name'],
                'email': row['email'],
                'competencies': competencies,
                'certifications': certifications,
                'cloud_skills': cloud_skills
            }
            employees.append(employee)
            
        print(f"Read {len(employees)} employees from CSV")
        return employees
    except Exception as e:
        print(f"Error reading employees CSV: {e}")
        return []

def read_pse_data_csv(file_path=PSE_DATA_CSV):
    """Read PSE (Project System of Engagement) data from CSV file"""
    try:
        df = pd.read_csv(file_path)
        
        # Group the PSE data by employee_id
        grouped_data = {}
        
        for _, row in df.iterrows():
            employee_id = row['employee_id']
            
            # Initialize the list for this employee if not already present
            if employee_id not in grouped_data:
                grouped_data[employee_id] = []
            
            # Convert row to dict and append to the employee's project list
            project_data = row.to_dict()
            grouped_data[employee_id].append(project_data)
        
        print(f"Read PSE data for {len(grouped_data)} employees")
        return grouped_data
    except Exception as e:
        print(f"Error reading PSE data CSV: {e}")
        return {}

def read_approved_values_csv(file_path=APPROVED_VALUES_CSV):
    """Read approved competencies from CSV file"""
    try:
        df = pd.read_csv(file_path)
        
        approved_competencies = df['approved_competency'].dropna().tolist() if 'approved_competency' in df.columns else []
        
        approved_values = {
            "approved_competencies": approved_competencies
        }
        
        print(f"Read {len(approved_competencies)} approved competencies")
        return approved_values
    except Exception as e:
        print(f"Error reading approved values CSV: {e}")
        return {"approved_competencies": []}

# -------------------------------
# Employee Analysis Function
# -------------------------------
def analyze_employee(employee, pse_data, approved_values):
    """Analyze employee skills and competencies using LLM"""
    print(f"\n{'='*50}")
    print(f"Analyzing Employee: {employee['name']} (ID: {employee['employee_id']})")
    print(f"{'='*50}")
    
    # Retrieve company approved competencies
    approved_competencies = approved_values.get("approved_competencies", [])
    
    # Get PSE data for this employee
    employee_pse_data = pse_data.get(employee['employee_id'], [])
    
    # Build the system prompt
    system_prompt = """You are a competency updater agent specializing in making sure an employee's competencies are aligned with company standards and up to date. You will be provided an employee's 
current certifications, cloud skills, existing approved competencies, and project history (PSE data). You will also be provided the company-approved list of competencies. Please do the following:

1. Analyze the employee's existing certifications, cloud skills, existing competencies listed, and project history
2. Compare their info to the company's approved competencies list
3. Determine which approved competencies are missing and should be added to their profile based on the information provided
4. Look at the certifications, cloud skills, and project history. Can we glean any approved competencies from these?
5. For each recommended competency, determine the appropriate skill level: beginner, intermediate, advanced, or expert

Our goal is to closely analyze all available information and produce a comprehensive list of company-approved competencies that the employee should have on their profile.

###Data Source Info###

Project history/PSE Data contains the projects the employee has worked on. Each project will have a list of the required competencies, certifications, and cloud skills. 
If the employee has worked on a project, and the project required a competency that the employee does not have listed in their existing approved competencies, then the employee is very likely missing that competency.


###Output Format###

1. thought_process: A comprehensive analysis of the employee's skills, certifications, existing approved competencies, and project history. What skills and certifications can map to approved competencies? What can we discern from the projects they worked on?

2. new_competencies: <new competency> <level: beginner/intermediate/advanced/expert> <confidence value> <reasoning - how did you come to this conclusion? what data points support this?>

For each competency, include:
- Competency name from the approved list
- Competency level (beginner, intermediate, advanced, or expert) based on evidence from their background
- A % confidence value (0-100). For obvious matches with the approved competencies, put 100%. For less obvious matches, put some % but be careful not to overstate the confidence.
- Detailed reasoning that supports both the competency and the assigned level
"""
    
    # Format PSE data for inclusion in the prompt
    pse_data_formatted = ""
    if employee_pse_data:
        pse_data_formatted = "Project History (PSE Data):\n"
        for idx, project in enumerate(employee_pse_data, 1):
            pse_data_formatted += f"Project {idx}:\n"
            for key, value in project.items():
                if key != 'employee_id':  # Skip employee_id as redundant
                    pse_data_formatted += f"  {key}: {value}\n"
            pse_data_formatted += "\n"
    else:
        pse_data_formatted = "Project History (PSE Data): No project history available\n"
    
    # Build the user message
    user_message = f"""### Employee Name: {employee['name']} ###
Existing Cloud Skills: {', '.join(employee['cloud_skills'])}
Existing Competencies:
{chr(10).join(f"- {comp}: {level}" for comp, level in employee['competencies'].items())}
Existing Certifications: {', '.join(employee['certifications'])}

{pse_data_formatted}

### Company Approved Competencies ###
{', '.join(approved_competencies)}
"""
    
    # Call the LLM
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message}
    ]
    
    llm_with_structured_output = llm.with_structured_output(CompetencyAnalysis)
    analysis_result = llm_with_structured_output.invoke(messages)

    # Print the raw values as requested
    print("\n===== RAW ANALYSIS VALUES =====")
    print(f"thought_process={analysis_result.thought_process}")
    
    print(f"\nnew_competencies=[")
    for comp in analysis_result.new_competencies:
        print(f"  {{competency='{comp.competency}', level='{comp.level}', confidence={comp.confidence}, reasoning='{comp.reasoning}'}},")
    print("]")
    
    # Create the text format for returning
    competencies_text = "\n".join([
        f"- {comp.competency} (Level: {comp.level}, Confidence: {comp.confidence}%)\n  Reasoning: {comp.reasoning}"
        for comp in analysis_result.new_competencies
    ])
    
    final_analysis = f"""
Complete Analysis for {employee['name']}
{'='*50}

Thought Process:
{analysis_result.thought_process}

Recommended New Competencies:
{competencies_text}

{'='*50}
"""
    
    # Return both the formatted text and the structured object
    return {
        "text": final_analysis,
        "structured_data": analysis_result
    }

# -------------------------------
# Email Notification Function
# -------------------------------
def send_notification(employee, analysis_result, cosmos_db_manager):
    """Send an email notification to the employee with their analysis"""
    print(f"\n{'='*50}")
    print(f"Processing notification for Employee: {employee['name']} (ID: {employee['employee_id']})")
    print(f"{'='*50}")
    
    notification_sent = False
    notification_timestamp = None
    
    if ENABLE_EMAIL_NOTIFICATIONS:
        # Get the employee's email
        employee_email = employee['email']
        
        # Extract text and structured data
        analysis_text = analysis_result["text"]
        structured_data = analysis_result["structured_data"]
        
        # Build the email subject and body
        subject = f"Skills & Competencies Update Recommendation for {employee['name']}"
        
        # Create a more structured HTML representation of the recommendations
        recommendations_html = ""
        for comp in structured_data.new_competencies:
            recommendations_html += f'''
            <div class="recommendation">
                <h3>{comp.competency} <span class="level">{comp.level}</span> <span class="confidence">({comp.confidence}% confidence)</span></h3>
                <p><strong>Reasoning:</strong> {comp.reasoning}</p>
            </div>
            '''
        
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
                        max-width: 800px;
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
                    h2 {{
                        font-size: 20px;
                        color: #444444;
                        margin-top: 20px;
                    }}
                    h3 {{
                        font-size: 18px;
                        color: #0066cc;
                        margin-bottom: 5px;
                    }}
                    .thought-process {{
                        background: #f9f9f9;
                        padding: 15px;
                        border-radius: 4px;
                        margin: 15px 0;
                        border-left: 4px solid #dddddd;
                    }}
                    .recommendations {{
                        margin-top: 20px;
                    }}
                    .recommendation {{
                        background: #f0f7ff;
                        padding: 15px;
                        border-radius: 4px;
                        margin-bottom: 15px;
                        border-left: 4px solid #0066cc;
                    }}
                    .level {{
                        color: #008800;
                        font-weight: bold;
                        margin-right: 8px;
                    }}
                    .confidence {{
                        color: #666666;
                        font-weight: normal;
                        font-size: 16px;
                    }}
                    .recommendations-link {{
                        color: #0066cc;
                        text-decoration: none;
                        margin-bottom: 15px;
                        display: inline-block;
                        padding: 10px 15px;
                        background: #e6f0ff;
                        border-radius: 4px;
                    }}
                    .recommendations-link:hover {{
                        background: #d4e6ff;
                        text-decoration: underline;
                    }}
                </style>
            </head>
            <body>
                <div class="container">
                    <h1>Skills &amp; Competencies Update Recommendation</h1>
                    <a href="http://localhost:3000/recommendations" class="recommendations-link">View and Validate Recommendations</a>
                    <p>Hello {employee['name']},</p>
                    <p>Based on our analysis of your profile, we've identified potential competencies to add to your profile:</p>
                    
                    <h2>Recommended Competencies</h2>
                    <div class="recommendations">
                        {recommendations_html}
                    </div>
                    
                    <h2>Analysis Details</h2>
                    <div class="thought-process">
                        {structured_data.thought_process}
                    </div>
                    
                    <p>Best regards,<br/>HR Team</p>
                </div>
            </body>
        </html>
        """
        
        # Build the email message
        email_message = {
            "senderAddress": SENDER_EMAIL,
            "recipients": {
                "to": [{"address": employee_email}]
            },
            "content": {
                "subject": subject,
                "plainText": analysis_text,
                "html": html_content
            }
        }
        
        # Send the email
        try:
            poller = email_client.begin_send(email_message)
            result = poller.result()
            print(f"Notification sent successfully to {employee_email}")
            notification_sent = True
            notification_timestamp = datetime.now().isoformat()
        except Exception as e:
            print(f"Failed to send email: {e}")
    else:
        print("Email notifications are disabled. Skipping email send.")
        # For development/testing purposes, we'll set notification_sent to True
        notification_sent = True
        notification_timestamp = datetime.now().isoformat()
    
            # Update the Cosmos DB record with notification info if sent
    if notification_sent:
        try:
            # Ensure employee_id is a string
            employee_id_str = str(employee['employee_id'])
            
            # Query for the existing record
            query = f"SELECT * FROM c WHERE c.employee_id = '{employee_id_str}'"
            existing_records = cosmos_db_manager.query_items(query)
            
            if existing_records:
                # Update existing record
                record = existing_records[0]
                record['notification_sent'] = True
                record['notification_timestamp'] = notification_timestamp
                
                cosmos_db_manager.update_item(record)
                print(f"Updated Cosmos DB record for employee {employee['employee_id']} with notification info")
            else:
                print(f"Warning: No Cosmos DB record found for employee {employee['employee_id']} to update notification status")
        
        except Exception as e:
            print(f"Error updating notification status in Cosmos DB: {e}")
    
    return {
        "notification_sent": notification_sent,
        "notification_timestamp": notification_timestamp
    }

# -------------------------------
# Store Employee Analysis in Cosmos DB
# -------------------------------
def store_employee_analysis(employee, analysis_result, cosmos_db_manager):
    """Store employee analysis results in Cosmos DB"""
    print(f"\n{'='*50}")
    print(f"Storing analysis for Employee: {employee['name']} (ID: {employee['employee_id']})")
    print(f"{'='*50}")
    
    try:
        # Ensure employee_id is a string for Cosmos DB
        employee_id_str = str(employee['employee_id'])
        
        # Create the employee record for Cosmos DB - only store essential information
        employee_record = {
            "id": employee_id_str,
            "partitionKey": "people",  # Using "people" as the partition key as requested
            "employee_id": employee_id_str,
            "employee_name": employee['name'],
            "employee_email": employee['email'],
            "analysis_result": analysis_result["structured_data"].model_dump(),  # Convert Pydantic model to dict
            "notification_sent": False,
            "notification_timestamp": None,
            "approved": False,
            "approved_timestamp": None,
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat()
        }
        
        # Instead of trying to determine if the record exists, use upsert which works for both create and update
        print(f"Upserting record for employee {employee_id_str}...")
        try:
            result = cosmos_db_manager.upsert_item(employee_record)
            if result:
                print(f"Successfully upserted record for {employee['name']} in Cosmos DB")
                return True
            else:
                print(f"Failed to upsert record for {employee['name']} in Cosmos DB - no result returned")
                return False
        except Exception as e:
            print(f"Error during upsert operation: {e}")
            return False
            
    except Exception as e:
        print(f"Error preparing employee record for Cosmos DB: {e}")
        import traceback
        traceback.print_exc()
        return False

# -------------------------------
# Main Function
# -------------------------------
def main():
    """Run the employee analysis workflow using structured outputs."""
    print("\n=== Employee Skills Analysis System ===")
    
    # Initialize Cosmos DB Manager
    try:
        cosmos_db_manager = CosmosDBManager(
            cosmos_database_id=COSMOS_DATABASE_ID,
            cosmos_container_id=COSMOS_CONTAINER_ID
        )
        print(f"Connected to Cosmos DB - Database: {COSMOS_DATABASE_ID}, Container: {COSMOS_CONTAINER_ID}")
    except Exception as e:
        print(f"Failed to connect to Cosmos DB: {e}")
        return
    
    # Load all data
    print("\nLoading data...")
    employees = read_employees_csv()
    pse_data = read_pse_data_csv()
    approved_values = read_approved_values_csv()
    
    print("\n==== EMPLOYEE ANALYSIS DETAILS ====")
    print(f"Total employees: {len(employees)}")
    
    # Set maximum number of employees to process (for testing purposes)
    MAX_EMPLOYEES = 3
    processed_count = 0
    skipped_count = 0
    success_count = 0
    
    # Loop through each employee
    for index, employee in enumerate(employees):
        employee_id = employee.get("employee_id", "N/A")
        name = employee.get("name", "N/A")
        
        print(f"\n--- Employee #{index+1}: {name} (ID: {employee_id}) ---")
        
        # Check competencies count
        competencies = employee.get("competencies", {})
        if competencies is None:
            competencies = {}
            print("  WARNING: competencies is None, treating as empty dict")
            employee["competencies"] = competencies
            
        print(f"  Competencies count: {len(competencies)}")
        if len(competencies) > 0:
            print(f"  Competencies: {competencies}")
        
        # Process if competencies count is less than 7
        if len(competencies) < 7 and processed_count < MAX_EMPLOYEES:
            print(f"  PROCESSING: Employee has {len(competencies)} competencies (< 7)")
            processed_count += 1
            
            # Analyze employee with structured output
            analysis_result = analyze_employee(employee, pse_data, approved_values)
            
            # Store analysis in Cosmos DB
            storage_success = store_employee_analysis(employee, analysis_result, cosmos_db_manager)
            
            # Send notification email and update notification status in Cosmos DB
            if storage_success:
                notification_result = send_notification(employee, analysis_result, cosmos_db_manager)
                if notification_result["notification_sent"]:
                    success_count += 1
        else:
            print(f"  SKIPPED: Employee has {len(competencies)} competencies (≥ 7) or max processed reached")
            skipped_count += 1
    
    # Provide simple processing summary
    print("\n==== PROCESSING SUMMARY ====")
    print(f"Total employees: {len(employees)}")
    print(f"Processed: {processed_count}")
    print(f"Successfully stored in Cosmos DB: {success_count}")
    print(f"Skipped: {skipped_count}")
    
    # Provide warning if no employees meet criteria
    if processed_count == 0 and len(employees) > 0:
        print("\n==== WARNING: No employees meet the criteria ====")
        print("All employees have 7 or more competencies")
    
    print("\n==== ANALYSIS COMPLETE ====")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {str(e)}")