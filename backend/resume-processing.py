from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from azure.core.credentials import AzureKeyCredential
from langchain_openai import AzureChatOpenAI
import os
from pydantic import BaseModel
from typing import List, Dict, Any, Union, Literal
from dotenv import load_dotenv
import json
import hashlib
from datetime import datetime, timezone
from cosmos_db import CosmosDBManager

load_dotenv()

# Storage account settings
storage_account_name = os.getenv("STORAGE_ACCOUNT_NAME")
container_name = "resumes"
tenant_id = os.getenv("TENANT_ID")

# Azure service configurations
form_recognizer_endpoint = os.getenv("FORM_RECOGNIZER_ENDPOINT")
form_recognizer_key = os.getenv("FORM_RECOGNIZER_KEY")
aoai_deployment = os.getenv("AOAI_DEPLOYMENT")
aoai_key = os.getenv("AOAI_KEY")
aoai_endpoint = os.getenv("AOAI_ENDPOINT")

# Initialize Azure credentials
credential = DefaultAzureCredential(
    interactive_browser_tenant_id=tenant_id,
    visual_studio_code_tenant_id=tenant_id,
    workload_identity_tenant_id=tenant_id,
    shared_cache_tenant_id=tenant_id
)

# Initialize clients
blob_service_client = BlobServiceClient(
    account_url=f"https://{storage_account_name}.blob.core.windows.net",
    credential=credential
)

document_intelligence_client = DocumentIntelligenceClient(
    form_recognizer_endpoint, 
    AzureKeyCredential(form_recognizer_key)
)

class ResumeParser(BaseModel):
    """Schema for review agent decisions"""
    skills: List[str]  # Indices of valid results
    projects: List[str]


# LLM Setup
llm = AzureChatOpenAI(
    azure_deployment=aoai_deployment,
    api_version="2024-05-01-preview",
    temperature=0,
    max_tokens=None,
    timeout=None,
    max_retries=2,
    api_key=aoai_key,
    azure_endpoint=aoai_endpoint
)

parser_llm = llm.with_structured_output(ResumeParser)

cosmos_db = CosmosDBManager()

resume_extraction_prompt = """You are an AI assistant. Your job is to read the input resume, 
and output a list of skills that the person has and a list of projects the person has worked on. There is no limit to the number of skills. Keep the project descriptions to 1-3 sentences. Each list entry should be of the format: '<project name> - <project description>'.

Example output:

skills: ['Data Architecture', 'Java', 'Python', 'SQL', 'Git', 'Docker', 'Kubernetes', 'AWS', 'Azure'] 
projects: ['Modern Data Warehouse - Built a data warehouse for a large enterprise using AWS Redshift and AWS Glue. The data warehouse was used to store and query data from various sources.', 'SQL Server Upgrade - Upgraded a SQL Server database from version 2012 to 2019. The upgrade was done to improve the performance of the database and to add new features.']

}"""




def extract_employee_id(filename):
    """Extract employee ID from filename."""
    # generate unique id for resume
    unique_id = hashlib.md5(filename.encode()).hexdigest()
    return unique_id

def read_pdf(input_file):
    """Read PDF content using Document Intelligence."""
    print(f"\n=== Reading PDF: {input_file} ===")
    blob_url = f"https://{storage_account_name}.blob.core.windows.net/{container_name}/{input_file}"
    analyze_request = {"urlSource": blob_url}
    poller = document_intelligence_client.begin_analyze_document("prebuilt-layout", analyze_request=analyze_request)
    result = poller.result()
    print(f"✓ Successfully extracted text from document. Length: {len(result.content)} characters")
    print("First 500 characters of content:", result.content[:500], "...\n")
    return result.content

def extract_resume_info(full_text):
    """Extract structured information from resume text using LLM."""
    print("\n=== Extracting Resume Information using LLM ===")
    print("Sending text to LLM. Length:", len(full_text))
    messages = [
        {"role": "system", "content": resume_extraction_prompt},
        {"role": "user", "content": full_text}
    ]
    print("### MESSAGES ###\n ", messages)
    response = parser_llm.invoke(messages)

    print("\nLLM Response:")
    print(response.skills)
    print(response.projects)
    print("✓ Successfully extracted resume information\n")
    return response.skills, response.projects

def process_resume(blob_name):
    """Process a single resume and store in Cosmos DB."""
    try:
        # Extract employee ID from filename
        employee_id = extract_employee_id(blob_name)
        
        # Read PDF content
        full_text = read_pdf(blob_name)
        
        # Extract structured information
        skills, projects = extract_resume_info(full_text)
        
        # Prepare document for Cosmos DB
        document = {
            'id': hashlib.md5(blob_name.encode()).hexdigest(),
            'partitionKey': 'skills',
            'employee_id': employee_id,
            'employee_name': "Dan Giannone",
            'resume_skills': skills,
            'resume_projects': projects
        }
        
        # Store in Cosmos DB
        
        cosmos_db.upsert_item(document)
        
        print(f"Successfully processed {blob_name}")
        return True
        
    except Exception as e:
        print(f"Error processing {blob_name}: {str(e)}")
        return False

def process_resumes(limit=1):
    """Process resumes in the source folder up to the specified limit.
    
    Args:
        limit (int): Maximum number of resumes to process. Default is 1.
    """
    container_client = blob_service_client.get_container_client(container_name)
    source_blobs = [blob for blob in container_client.list_blobs() if blob.name.startswith("source/")]
    for blob in source_blobs:
        print(blob.name)
    
    print(f"Found {len(source_blobs)} resumes in source folder")
    print(f"Will process up to {limit} resume(s)")
    
    processed_count = 0
    for blob in source_blobs:
        if processed_count >= limit:
            break
            
        if process_resume(blob.name):
            # Move to processed folder after successful processing
            destination_blob_name = blob.name.replace("source/", "processed/")
            source_blob = container_client.get_blob_client(blob.name)
            destination_blob = container_client.get_blob_client(destination_blob_name)
            
            destination_blob.start_copy_from_url(source_blob.url)
            source_blob.delete_blob()
            print(f"Processed {processed_count} of {limit} resumes")
    
        processed_count += 1

    print(f"Finished processing {processed_count} resume(s)")

def move_blob(source_container_client, destination_container_client, source_blob_name, destination_blob_name):
    source_blob = source_container_client.get_blob_client(source_blob_name)
    destination_blob = destination_container_client.get_blob_client(destination_blob_name)
    
    destination_blob.start_copy_from_url(source_blob.url)
    source_blob.delete_blob()

def list_blobs_in_folder(container_client, folder_name):
    return [blob for blob in container_client.list_blobs() if blob.name.startswith(folder_name)]

def reset_processed_files():
    """Move all files from the 'processed' folder back to the 'source' folder."""
    container_client = blob_service_client.get_container_client(container_name)
    
    processed_blobs = list_blobs_in_folder(container_client, "processed/")
    
    for blob in processed_blobs:
        source_blob_name = blob.name
        destination_blob_name = source_blob_name.replace("processed/", "source/")
        
        try:
            # Move the blob back to the 'source' folder
            move_blob(container_client, container_client, source_blob_name, destination_blob_name)
        except Exception as e:
            print(f"Error moving {source_blob_name} back to 'source': {str(e)}")
    

if __name__ == "__main__":
    # Process just one resume
    blob_name = "source/Dan Giannone Resume.docx"

    reset_processed_files()
    #process_resumes(limit=0)
    process_resume(blob_name)




    

    
    


    

