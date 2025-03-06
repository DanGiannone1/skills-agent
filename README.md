# Employee Competencies Recommendation System

A comprehensive system that uses AI to analyze employee skills and automatically recommend competencies to add to their professional profile, with an approval workflow.

## System Overview

This project consists of two main components:

1. **Background Processing Agent** (`agent.py`): Analyzes employee data against company standards to identify missing competencies, uses AI to determine appropriate skill levels, and stores results in Cosmos DB.

2. **Web-based Approval UI**: A React frontend that allows employees to review, modify, and approve the recommended competencies for their profile.

## System Flow

1. The background agent processes employee data periodically:
   - Reads employee data from CSV files (competencies, certifications, skills)
   - Analyzes project history and existing skills
   - Uses Azure OpenAI to generate competency recommendations with confidence levels and reasoning
   - Stores results in Azure Cosmos DB
   - Optionally sends email notifications to employees

2. Employees receive notification emails with a link to the approval UI:
   - They review recommended competencies with detailed reasoning
   - They can approve all or reject specific recommendations
   - They can adjust skill levels for each competency (beginner → intermediate → advanced → expert)
   - Approved competencies are recorded in Cosmos DB

## Prerequisites

- Python 3.8+ for the background agent
- Node.js 16+ for the frontend
- Azure account with:
  - Azure Cosmos DB
  - Azure OpenAI Service
  - Azure Communication Services (for email notifications)
- Sample data files (CSV format)

## Local Setup

### 1. Clone the Repository

```bash
# Clone the repo to your local machine
git clone <repository-url>
cd <repository-directory>
```

### 2. Backend Setup

Create a Python virtual environment:

```bash
# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

Configure environment variables:

```bash
# Copy the example.env file to .env
cp example.env .env

# Edit the .env file with your specific configuration values
```

The example.env file includes templates for:

```
# Azure OpenAI Configuration
AOAI_DEPLOYMENT=your-openai-deployment-name
AOAI_KEY=your-openai-api-key
AOAI_ENDPOINT=https://your-openai-resource.openai.azure.com

# Azure Cosmos DB Configuration
COSMOS_HOST=https://your-cosmosdb-account.documents.azure.com:443/
COSMOS_DATABASE_ID=test_db
COSMOS_CONTAINER_ID=people

# Azure Communication Services (for email)
COMMUNICATION_SERVICES_CONNECTION_STRING=your-connection-string
SENDER_EMAIL=noreply@yourdomain.com


```

### 3. Frontend Setup

```bash
# Navigate to the frontend directory
cd frontend

# Install dependencies
npm install
```

Configure environment variables (create a `.env.local` file in the frontend directory):

```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

## Running the System

### 1. Start the Backend API Server

```bash
# From the backend directory
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

### 2. Run the Background Agent (Manually)

The agent can be run on demand or scheduled to run periodically:

```bash
# From the backend directory
python agent.py
```

For production, you might want to set up a cron job or Azure Functions to run this periodically.

### 3. Start the Frontend

```bash
# From the frontend directory
npm run dev
```

The application will be available at `http://localhost:3000/recommendations`.

## Customization Options

### Modifying Competency Analysis

Edit the `system_prompt` in `agent.py` to adjust how the agent analyzes employee skills and assigns confidence levels and competency ratings.

### Adjusting Email Notifications

- Set `ENABLE_EMAIL_NOTIFICATIONS = True` in `agent.py` to enable email sending
- Customize the email HTML template in the `send_notification` function

### Data Sources

By default, the system uses CSV files for employee data. The data sources can be adjusted by:

1. Modifying the CSV reading functions in `agent.py`
2. Creating custom data connectors for your specific HR systems

## Project Structure

TBD

## Data Requirements

Use your own data sources

## Cosmos DB Structure

The system uses a container named `people` with partition key set to "people" for all records.

Each document contains:
- Employee identification (`id`, `employee_id`, `employee_name`, `employee_email`)
- Recommendation results from AI analysis (`analysis_result`)
- Notification and approval status tracking

## Troubleshooting

### API Connection Issues

If the frontend can't connect to the backend:
- Verify the API is running on the correct port
- Check that CORS is properly configured in the API
- Confirm the frontend environment variables are set correctly

### Data Processing Problems

- Check the CSV file formats match the expected structure
- Verify Azure OpenAI credentials are correct
- Review the agent log outputs for error messages

## Security Considerations

For production environments:
- Restrict CORS to specific origins
- Implement proper authentication for the API
- Use Azure Key Vault for storing secrets
- Consider implementing row-level security in Cosmos DB