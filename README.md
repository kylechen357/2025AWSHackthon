# 不銹鋼國際規範 AI 助理系統

一個基於 AWS 的智能系統，協助華新麗華公司技術人員處理不銹鋼國際規範標準相關問題。本系統透過 AI 技術提供專業規範查詢、標準比較和文件分析服務，並根據用戶專業程度自動調整回答深度。

## 系統功能

- **專業標準查詢**：快速查詢 ASTM、JIS、EN 等國際規範中的鋼種成分、機械性質和產品適用範圍
- **多規範比較**：自動比對不同國際標準間的差異與對應關係
- **文件分析**：支援上傳 PDF、Excel、圖片等格式文件進行智能分析
- **專業度適應**：根據用戶的專業水平（初學者/中級/專家）自動調整回應的專業深度
- **網絡搜索增強**：對於知識庫中缺少的信息，可進行網絡搜索獲取最新資料

## 技術架構

### 前端技術
- HTML5 / CSS3 / JavaScript
- Bootstrap 5 框架
- Marked.js (Markdown 渲染)

### 後端服務
- **AWS Lambda**：核心業務邏輯處理
- **Amazon API Gateway**：API 管理
- **Amazon CloudFront**：內容分發網絡
- **Amazon S3**：靜態網站託管和文件存儲
- **Amazon DynamoDB**：對話歷史存儲
- **Amazon Kendra**：知識庫索引和查詢
- **Amazon Bedrock**：Claude 大型語言模型
- **Amazon Textract**：文件文本提取
- **Amazon Rekognition**：圖像分析
- **Amazon Comprehend**：文本分析和理解

## 系統處理流程

1. **輸入處理階段**：接收用戶問題和上傳文件，進行初步處理
2. **專業度評估階段**：分析用戶問題中的專業術語和問題複雜度，評估用戶專業水平
3. **內容檢索階段**：從知識庫查詢相關資料，必要時進行網絡搜索
4. **AI 生成階段**：使用 Claude 語言模型生成符合用戶專業水平的回答

## 專業度適應機制

系統能夠識別用戶的專業水平，並相應調整回答方式：

- **初學者模式**：提供基礎解釋，解釋專業術語，使用簡單語言
- **中級模式**：提供更詳細的技術信息，但仍附帶必要的背景說明
- **專家模式**：直接使用專業術語，提供詳細技術數據和深入分析

## 部署指南

### 前置需求
- AWS 帳戶
- Node.js 14+ (本地開發)
- Python 3.8+ (Lambda 函數)

### 部署步驟

1. **設置 S3 靜態網站**
   ```bash
   aws s3 mb s3://your-bucket-name
   aws s3 website s3://your-bucket-name --index-document app.html
   ```

2. **上傳前端文件**
   ```bash
   aws s3 cp app.html s3://your-bucket-name/
   aws s3 cp app.js s3://your-bucket-name/
   ```

3. **部署 Lambda 函數**
   ```bash
   cd lambda
   zip -r function.zip .
   aws lambda create-function --function-name SteelAssistantFunction \
     --runtime python3.8 --handler lambda.lambda_handler \
     --zip-file fileb://function.zip \
     --role arn:aws:iam::your-account-id:role/your-lambda-role
   ```

4. **設置 API Gateway**
   ```bash
   aws apigateway create-rest-api --name SteelAssistantAPI
   # 設置資源、方法和整合 (詳細步驟略)
   ```

5. **設置 CloudFront 分發**
   ```bash
   aws cloudfront create-distribution \
     --origin-domain-name your-bucket-name.s3-website-region.amazonaws.com
   ```

6. **設置 DynamoDB 表**
   ```bash
   aws dynamodb create-table --table-name SteelAssistantConversations \
     --attribute-definitions AttributeName=user_id,AttributeType=S \
     AttributeName=timestamp_session,AttributeType=S \
     --key-schema AttributeName=user_id,KeyType=HASH \
     AttributeName=timestamp_session,KeyType=RANGE \
     --provisioned-throughput ReadCapacityUnits=5,WriteCapacityUnits=5
   ```

## 環境變數配置

Lambda 函數需要以下環境變數：

| 變數名 | 說明 |
|-------|------|
| `KENDRA_INDEX_ID` | Amazon Kendra 索引 ID |
| `MODEL_ID` | Bedrock 模型 ID (預設為 Claude 3 Sonnet) |
| `CONVERSATION_TABLE` | DynamoDB 對話歷史表名 |
| `GOOGLE_API_KEY` | (可選) Google 搜索 API 金鑰 |
| `GOOGLE_SEARCH_ENGINE_ID` | (可選) Google 自定義搜索引擎 ID |
| `WEB_SEARCH_ENABLED` | 是否啟用網絡搜索 (true/false) |


## 未來工作

- 擴展知識庫覆蓋更多的國際標準
- 實現多語言支持 (英文、日文等)
- 加強表格和圖表識別能力
- 開發專用的移動應用
