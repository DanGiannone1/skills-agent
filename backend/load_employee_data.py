""" Script to load employee data from JSON file into Cosmos DB. Each employee will have two documents: 
one for skills (including certifications) and one for projects. """

import json
from cosmos_db import CosmosDBManager

def validate_employee_data(data):
    """Validate the structure of the employee data."""
    required_fields = {
        'metadata': ['approved_skills', 'approved_competencies'],
        'employee_skills': ['id', 'name', 'approved_skills', 'competencies', 'free_text_skills', 'certifications'],
        'employee_projects': ['id', 'name', 'projects']
    }
    
    for section, fields in required_fields.items():
        if section not in data:
            raise ValueError(f"Missing required section: {section}")
        
        if section == 'metadata':
            for field in fields:
                if field not in data[section]:
                    raise ValueError(f"Missing required field in metadata: {field}")
        else:
            for item in data[section]:
                for field in fields:
                    if field not in item:
                        raise ValueError(f"Missing required field '{field}' in {section} for employee: {item.get('name', 'Unknown')}")

def load_data_to_cosmos():
    """Load the employee data from JSON into Cosmos DB."""
    # Initialize Cosmos DB manager
    cosmos_db = CosmosDBManager()
    
    # Read the JSON file
    try:
        with open('employee_data.json', 'r') as f:
            data = json.load(f)
        
        # Validate data structure
        validate_employee_data(data)
    except FileNotFoundError:
        print("Error: employee_data.json file not found in the backend directory")
        return
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON format in employee_data.json: {str(e)}")
        return
    except ValueError as e:
        print(f"Error: Data validation failed: {str(e)}")
        return
    
    # Store metadata as a separate document
    metadata = {
        'id': 'skills_metadata',
        'partitionKey': 'metadata',
        'type': 'metadata',
        **data['metadata']
    }
    print("Loading metadata...")
    result = cosmos_db.upsert_item(metadata)
    if result:
        print("Successfully loaded metadata")
    else:
        print("Failed to load metadata")
    
    # Load employee skills
    print("\nLoading employee skills...")
    for skill_doc in data['employee_skills']:
        employee_doc = {
            **skill_doc,
            'partitionKey': 'employee',
            'type': 'skills'  # Ensure type is explicitly set
        }
        print(f"Loading skills for employee: {employee_doc['name']}")
        result = cosmos_db.upsert_item(employee_doc)
        if result:
            print(f"Successfully loaded skills for {employee_doc['name']}")
        else:
            print(f"Failed to load skills for {employee_doc['name']}")
    
    # Load employee projects
    print("\nLoading employee projects...")
    for project_doc in data['employee_projects']:
        project_history_doc = {
            **project_doc,
            'partitionKey': 'project_history',
            'type': 'projects'  # Ensure type is explicitly set
        }
        print(f"Loading projects for employee: {project_history_doc['name']}")
        result = cosmos_db.upsert_item(project_history_doc)
        if result:
            print(f"Successfully loaded projects for {project_history_doc['name']}")
        else:
            print(f"Failed to load projects for {project_history_doc['name']}")

if __name__ == "__main__":
    try:
        load_data_to_cosmos()
        print("\nData loading completed!")
    except Exception as e:
        print(f"An error occurred while loading data: {str(e)}")
        raise  # Re-raise the exception for debugging purposes