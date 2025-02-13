#agent.py
from typing import List, Dict, Any
from cosmos_db import CosmosDBManager

# Initialize the global CosmosDB connection
cosmos_db = CosmosDBManager()

def get_employees_with_few_skills(max_skills: int = 5) -> List[Dict[str, Any]]:
    """
    Get employees who have fewer than the specified number of approved skills.
    
    Args:
        max_skills (int): Maximum number of approved skills threshold (default: 5)
        
    Returns:
        List[Dict]: List of employee documents with their skill information
    """
    query = f"""
    SELECT * FROM c 
    WHERE c.partitionKey = 'employee' 
    AND ARRAY_LENGTH(c.approved_skills) < {max_skills}
    """
    return list(cosmos_db.query_items(query))

def get_project_history(employee_ids: List[str]) -> List[Dict[str, Any]]:
    """
    Get project history for specified employees.
    
    Args:
        employee_ids (List[str]): List of employee IDs to fetch project history for
        
    Returns:
        List[Dict]: List of project history documents for the specified employees
    """
    employee_ids_str = ", ".join([f"'{id}'" for id in employee_ids])
    query = f"""
    SELECT * FROM c 
    WHERE c.partitionKey = 'project_history' 
    AND c.employee_id IN ({employee_ids_str})
    """
    return list(cosmos_db.query_items(query))

def get_skills_metadata() -> Dict[str, Any]:
    """
    Get skills metadata including approved skills and competencies.
    
    Returns:
        Dict: Metadata document containing approved skills and competencies
    """
    query = """
    SELECT * FROM c 
    WHERE c.partitionKey = 'metadata' 
    AND c.id = 'skills_metadata'
    """
    results = list(cosmos_db.query_items(query))
    return results[0] if results else None

def main():
    """Test the skills agent functionality."""
    # Print section header
    def print_section(num, title):
        print(f"\n{num}. {title}")
        print("-" * 50)
    
    # Print separator line
    def print_separator(char="-", length=30):
        print(char * length)
    
    print_section(1, "Testing get_employees_with_few_skills()")
    employees = get_employees_with_few_skills(max_skills=7)
    
    if not employees:
        print("No employees found with fewer than 7 approved skills.")
    else:
        for emp in employees:
            name = emp.get('name', 'Unknown Employee')
            skills = emp.get('approved_skills', [])
            competencies = emp.get('competencies', {})
            free_text = emp.get('free_text_skills', [])
            
            print(f"\nEmployee: {name}")
            print(f"Approved Skills ({len(skills)}): {', '.join(skills)}")
            
            if competencies:
                print("\nCompetencies:")
                for comp, level in sorted(competencies.items()):
                    print(f"- {comp}: {level}")
            
            if free_text:
                print("\nFree Text Skills:")
                for skill in sorted(free_text):
                    print(f"- {skill}")
            print_separator()
    
    print_section(2, "Testing get_project_history()")
    projects = get_project_history(employee_ids=["DG001", "MR001"])
    
    if not projects:
        print("No project history found for the specified employees.")
    else:
        for proj in projects:
            name = proj.get('name', 'Unknown Employee')
            project_list = proj.get('projects', [])
            
            print(f"\nEmployee: {name}")
            print_separator()
            
            if project_list:
                for p in project_list:
                    print(f"\nProject: {p.get('name', 'Unnamed Project')}")
                    print(f"Role: {p.get('role', 'Role not specified')}")
                    print(f"Duration: {p.get('duration', 'Duration not specified')}")
                    
                    description = p.get('description', 'No description available')
                    # Split description into lines if it's too long
                    if len(description) > 80:
                        words = description.split()
                        lines = []
                        current_line = []
                        
                        for word in words:
                            if len(' '.join(current_line + [word])) <= 80:
                                current_line.append(word)
                            else:
                                lines.append(' '.join(current_line))
                                current_line = [word]
                        if current_line:
                            lines.append(' '.join(current_line))
                            
                        print("Description:")
                        for line in lines:
                            print(f"  {line}")
                    else:
                        print(f"Description: {description}")
                    print_separator("-", 20)
            else:
                print("No projects found for this employee")
    
    print_section(3, "Testing get_skills_metadata()")
    metadata = get_skills_metadata()
    
    if metadata:
        skills = metadata.get('approved_skills', [])
        competencies = metadata.get('approved_competencies', [])
        
        if skills:
            print("Approved Skills:")
            for skill in sorted(skills):
                print(f"- {skill}")
        
        if competencies:
            print("\nApproved Competencies:")
            for comp in sorted(competencies):
                print(f"- {comp}")
    else:
        print("No skills metadata found.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {str(e)}")