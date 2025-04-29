
# Stainless Steel International Standards AI Assistant System

An AWS-based intelligent system designed to assist technical personnel at Walsin Lihwa Corporation with questions related to international standards for stainless steel. The system leverages AI technologies to provide professional standard queries, standard comparisons, and document analysis services, automatically adjusting response complexity based on user expertise.


https://github.com/user-attachments/assets/0c919aa5-f6b6-4eba-81ef-e9265f9d2345


## System Features

- **Professional Standard Queries:** Quickly search for steel grades, compositions, mechanical properties, and application scopes in ASTM, JIS, EN, and other international standards.
- **Multi-standard Comparisons:** Automatically compare differences and correspondences among various international standards.
- **Document Analysis:** Supports intelligent analysis of documents in PDF, Excel, and image formats.
- **Expertise Adaptation:** Automatically adjusts the depth of responses based on user proficiency levels (beginner/intermediate/expert).
- **Enhanced Web Search:** Performs web searches to retrieve the latest information when knowledge base data is insufficient.

## Technical Architecture

### Front-end Technologies
- HTML5 / CSS3 / JavaScript
- Bootstrap 5 Framework
- Marked.js (Markdown rendering)

### Backend Services
- **AWS Lambda:** Core business logic processing
- **Amazon API Gateway:** API management
- **Amazon CloudFront:** Content delivery network
- **Amazon S3:** Static website hosting and file storage
- **Amazon DynamoDB:** Conversation history storage
- **Amazon Kendra:** Knowledge base indexing and querying
- **Amazon Bedrock:** Claude large language model
- **Amazon Textract:** Document text extraction
- **Amazon Rekognition:** Image analysis
- **Amazon Comprehend:** Text analysis and comprehension

## System Workflow

1. **Input Processing Stage:** Receives and initially processes user questions and uploaded documents.
2. **Expertise Evaluation Stage:** Analyzes professional terminology and complexity in user queries to evaluate user expertise.
3. **Content Retrieval Stage:** Queries the knowledge base for relevant data, performing web searches if necessary.
4. **AI Generation Stage:** Generates responses tailored to user expertise levels using the Claude language model.

## Expertise Adaptation Mechanism

The system identifies the user's proficiency and adjusts responses accordingly:

- **Beginner Mode:** Provides basic explanations, defines professional terms, and uses simple language.
- **Intermediate Mode:** Offers detailed technical information with essential background explanations.
- **Expert Mode:** Directly utilizes professional terms, presenting detailed technical data and in-depth analysis.

## Deployment Guide

### Prerequisites
- AWS account
- Node.js 14+ (for local development)
- Python 3.8+ (for Lambda functions)

### Deployment Steps

1. **Set up an S3 Static Website**
   ```bash
   aws s3 mb s3://your-bucket-name
   aws s3 website s3://your-bucket-name --index-document app.html
   ```

2. **Upload Front-end Files**
   ```bash
   aws s3 cp app.html s3://your-bucket-name/
   aws s3 cp app.js s3://your-bucket-name/
   ```

3. **Deploy Lambda Functions**
   ```bash
   cd lambda
   zip -r function.zip .
   aws lambda create-function --function-name SteelAssistantFunction \
     --runtime python3.8 --handler lambda.lambda_handler \
     --zip-file fileb://function.zip \
     --role arn:aws:iam::your-account-id:role/your-lambda-role
   ```

4. **Set up API Gateway**
   ```bash
   aws apigateway create-rest-api --name SteelAssistantAPI
   # Set up resources, methods, and integrations (details omitted)
   ```

5. **Set up CloudFront Distribution**
   ```bash
   aws cloudfront create-distribution \
     --origin-domain-name your-bucket-name.s3-website-region.amazonaws.com
   ```

6. **Set up DynamoDB Table**
   ```bash
   aws dynamodb create-table --table-name SteelAssistantConversations \
     --attribute-definitions AttributeName=user_id,AttributeType=S \
     AttributeName=timestamp_session,AttributeType=S \
     --key-schema AttributeName=user_id,KeyType=HASH \
     AttributeName=timestamp_session,KeyType=RANGE \
     --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5
   ```

## Environment Variables Configuration

Lambda functions require the following environment variables:

| Variable Name              | Description                                   |
|----------------------------|-----------------------------------------------|
| `KENDRA_INDEX_ID`          | Amazon Kendra Index ID                         |
| `MODEL_ID`                 | Bedrock Model ID (default is Claude 3 Sonnet)  |
| `CONVERSATION_TABLE`       | DynamoDB conversation history table name       |
| `GOOGLE_API_KEY`           | (Optional) Google Search API Key               |
| `GOOGLE_SEARCH_ENGINE_ID`  | (Optional) Google Custom Search Engine ID      |
| `WEB_SEARCH_ENABLED`       | Enable web search (true/false)                 |

## License and Usage

This project is for internal use by Walsin Lihwa Corporation. Unauthorized commercial use is prohibited.

## Future Work

- Expand the knowledge base to cover more international standards.
- Implement multi-language support (English, Japanese, etc.).
- Enhance the recognition capabilities for tables and charts.
- Develop a dedicated mobile application.
