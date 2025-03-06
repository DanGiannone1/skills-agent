from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from cosmos_db import CosmosDBManager
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import json

# Define models for our API responses
class CompetencyRecommendation(BaseModel):
    id: str
    name: str  # This is the competency name
    level: str  # One of: "beginner", "intermediate", "advanced", "expert"
    confidence: int  # Percentage (0-100)
    reasoning: str = Field(..., description="The reasoning provided by the agent")

class EmployeeRecommendations(BaseModel):
    employee_id: str
    employee_name: str
    recommendations: List[CompetencyRecommendation]

# Initialize FastAPI app
app = FastAPI(title="Employee Competencies API")

# Add CORS middleware to allow frontend to call our API
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For development; restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cosmos DB configuration
DATABASE_ID = "test_db"
CONTAINER_ID = "people"

# Create a CosmosDBManager instance
cosmos_manager = CosmosDBManager(
    cosmos_database_id=DATABASE_ID,
    cosmos_container_id=CONTAINER_ID
)

# Function to get recommendations for an employee
def get_employee_recommendations(employee_id: str):
    try:
        # Query for the employee document
        query = "SELECT * FROM c WHERE c.employee_id = @employee_id AND c.partitionKey = 'people'"
        parameters = [{"name": "@employee_id", "value": employee_id}]
        
        items = cosmos_manager.query_items(
            query=query,
            parameters=parameters
        )
        
        if not items:
            raise HTTPException(status_code=404, detail=f"Employee {employee_id} not found")
        
        employee_record = items[0]
        print(f"Raw employee record: {json.dumps(employee_record, indent=2)}")
        
        # Extract and format recommendations
        recommendations = []
        
        if 'analysis_result' in employee_record and 'new_competencies' in employee_record['analysis_result']:
            print(f"Found {len(employee_record['analysis_result']['new_competencies'])} competencies")
            
            for i, comp in enumerate(employee_record['analysis_result']['new_competencies']):
                print(f"Processing competency {i+1}: {comp}")
                
                # Create the recommendation with explicit debug for each field
                try:
                    recommendation = CompetencyRecommendation(
                        id=str(i+1),
                        name=comp['competency'],
                        level=comp['level'],
                        confidence=comp['confidence'],
                        reasoning=comp.get('reasoning', "No reasoning provided")
                    )
                    print(f"Created recommendation: {recommendation}")
                    recommendations.append(recommendation)
                except Exception as e:
                    print(f"Error creating recommendation object: {e}")
                    # Try to create with debug info
                    recommendation = CompetencyRecommendation(
                        id=str(i+1),
                        name=comp.get('competency', 'Unknown'),
                        level=comp.get('level', 'beginner'),
                        confidence=comp.get('confidence', 0),
                        reasoning=f"Error processing: {str(e)}"
                    )
                    recommendations.append(recommendation)
            
            # Sort recommendations by confidence (highest first)
            recommendations.sort(key=lambda x: x.confidence, reverse=True)
        
        result = EmployeeRecommendations(
            employee_id=employee_record['employee_id'],
            employee_name=employee_record['employee_name'],
            recommendations=recommendations
        )
        
        # Debug the final result - fix the deprecated json method
        print(f"Final API response: {result.model_dump_json(indent=2)}")
        return result
    
    except Exception as e:
        import traceback
        print(f"Error retrieving recommendations: {str(e)}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Error: {str(e)}")

# Define API endpoints
@app.get("/api/recommendations/{employee_id}", response_model=EmployeeRecommendations)
def read_recommendations(employee_id: str):
    return get_employee_recommendations(employee_id)

# For testing - hardcoded endpoint for employee 11707953
@app.get("/api/recommendations", response_model=EmployeeRecommendations)
def read_hardcoded_recommendations():
    return get_employee_recommendations("11707953")

# Root endpoint
@app.get("/")
def root():
    return {"message": "Employee Competencies API is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)