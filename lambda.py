import json
import boto3
import os
import io
import base64
import requests
import pandas as pd
import numpy as np
import re
import time
from urllib.parse import unquote_plus
from bs4 import BeautifulSoup
from datetime import datetime
import traceback

# 初始化AWS客戶端
bedrock = boto3.client('bedrock-runtime')
kendra = boto3.client('kendra')
s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')
textract = boto3.client('textract')     
rekognition = boto3.client('rekognition')  
comprehend = boto3.client('comprehend')   

# 環境變數
KENDRA_INDEX_ID = os.environ.get('KENDRA_INDEX_ID', 'bb62d174-7a66-495c-9fdd-cad8d7d2c223')
MODEL_ID = os.environ.get('MODEL_ID', 'anthropic.claude-3-sonnet-20240229-v1:0')
CONVERSATION_TABLE = os.environ.get('CONVERSATION_TABLE', 'SteelAssistantConversations')
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY', '')
GOOGLE_SEARCH_ENGINE_ID = os.environ.get('GOOGLE_SEARCH_ENGINE_ID', '')
WEB_SEARCH_ENABLED = os.environ.get('WEB_SEARCH_ENABLED', 'false').lower() == 'true'
BEDROCK_WEB_SEARCH = os.environ.get('BEDROCK_WEB_SEARCH', 'false').lower() == 'true'

# DynamoDB表引用
conversation_table = dynamodb.Table(CONVERSATION_TABLE)

def lambda_handler(event, context):
    """處理API Gateway傳入的請求或直接測試請求"""
    try:
        print("Received event:", json.dumps(event))
        
        # 處理不同的輸入格式
        if isinstance(event, dict):
            if 'body' in event:
                # API Gateway 格式
                if isinstance(event['body'], str):
                    body = json.loads(event['body'])
                else:
                    body = event['body']
            else:
                # 直接測試格式
                body = event
        else:
            body = {'message': str(event)}
        
        print("Processed body:", json.dumps(body))
        
        user_id = body.get('user_id', 'anonymous')
        message = body.get('message', '')
        session_id = body.get('session_id', f'test_{int(time.time())}')
        
        file_content = None
        file_type = None
        file_key = None
        extracted_text = ""
        file_analysis = None  # 初始化這個變數
        
        if 'file' in body and body['file']:
            file_data = body['file']
            file_content = base64.b64decode(file_data['content'])
            file_type = file_data['type']
            file_name = file_data['name']
            
            # 上傳檔案到S3
            file_key = f"uploads/{user_id}/{session_id}/{datetime.now().strftime('%Y%m%d%H%M%S')}_{file_name}"
            s3.put_object(
                Bucket='stainless-steel-standards-docs',
                Key=file_key,
                Body=file_content
            )
            
            # 分析檔案內容
            try:
                file_analysis = analyze_file(file_key, file_type, file_content)
                if file_analysis and isinstance(file_analysis, dict) and 'extracted_text' in file_analysis:
                    extracted_text = file_analysis.get('extracted_text', '')
            except Exception as e:
                print(f"File analysis error: {str(e)}")
                file_analysis = {
                    'success': False,
                    'error': str(e),
                    'extracted_text': ''
                }
            
            # 上傳檔案到S3
            file_key = f"uploads/{user_id}/{session_id}/{datetime.now().strftime('%Y%m%d%H%M%S')}_{file_name}"
            s3.put_object(
                Bucket='stainless-steel-standards-docs',
                Key=file_key,
                Body=file_content
            )
            
            # 分析檔案內容
            try:
                file_analysis = analyze_file(file_key, file_type, file_content)
                if file_analysis and isinstance(file_analysis, dict) and 'extracted_text' in file_analysis:
                    extracted_text = file_analysis.get('extracted_text', '')
            except Exception as e:
                print(f"File analysis error: {str(e)}")
                file_analysis = {
                    'success': False,
                    'error': str(e),
                    'extracted_text': ''
                }
        
        # 獲取對話歷史
        conversation_history = get_conversation_history(user_id, session_id)
        
        # 簡化版用戶專業度評估
        expertise_level = "beginner"  # 預設為初學者
        
        # 檢查消息中的專業術語和標準引用
        technical_terms = ["奧氏體", "肥粒體", "馬氏體", "固溶處理", "時效硬化", "PREN", "晶間腐蝕"]
        standards_regex = r'[A-Z]{2,5}\s*[A-Z]?[0-9]{1,5}(-[0-9]+)?'
        
        term_count = sum(1 for term in technical_terms if term.lower() in message.lower())
        standards_count = len(re.findall(standards_regex, message))
        
        if term_count >= 3 or standards_count >= 2:
            expertise_level = "expert"
        elif term_count >= 1 or standards_count >= 1:
            expertise_level = "intermediate"
        
        enhanced_system_prompt = f"""你是一個專業的不銹鋼國際規範AI助理，專門協助華新麗華公司的技術人員處理客戶訂單相關問題。
                            你擅長處理國際規範標準(ASTM、JIS、EN等)與規範項目(鋼種成分、尺寸公差、試驗標準等)的相關問題。

                            **使用者專業程度**: {expertise_level} (初學者/中級/專家)

                            **重要指示**:
                            1. 絕對不要向用戶請求提供額外資訊，如果不知道特定資訊，必須自行從已提供的資料中推斷或明確表示無法回答。
                            2. 在回答前，先進行深度思考：分析問題核心、評估可用資訊、應用專業知識、規劃回答結構。
                            3. 根據用戶專業程度調整回答:
                            - 初學者: 提供基礎解釋，解釋專業術語，使用簡單語言
                            - 中級: 提供更詳細的技術信息，但仍附帶必要的背景說明
                            - 專家: 直接使用專業術語，提供詳細技術數據和深入分析

                            4. 回答應包含充分的細節，並盡可能以表格形式呈現比較結果。
                            5. 對比較結果要仔細計算化學成分區間，確保多個標準的要求都能滿足。
                            6. 使用現有資訊作出最佳判斷，即使不確定也要提供有幫助的回答。"""
        
        
        # 獲取Kendra查詢結果
        kendra_results = query_kendra(message)
        
        # 強制對標準相關問題進行網絡搜索
        standards_keywords = ["ASTM", "EN", "ISO", "JIS", "DIN", "UNS", "AISI", "SAE",
                            "標準", "規範", "對應", "比較", "相當"]
        force_web_search = any(keyword in message for keyword in standards_keywords)
        requires_web_search = force_web_search or (WEB_SEARCH_ENABLED and check_if_requires_web_search(message, kendra_results))
        
        web_results = []
        detailed_content = []
        
        if requires_web_search:
            prompt = construct_prompt_with_web_results(
                message, conversation_history, kendra_results, 
                web_results, detailed_content, file_content, file_type, file_key,
                extracted_text=extracted_text, file_analysis=file_analysis,
                enhanced_system_prompt=enhanced_system_prompt
            )
        else:
            prompt = construct_prompt(
                message, conversation_history, kendra_results, 
                file_content, file_type, file_key,
                extracted_text=extracted_text, file_analysis=file_analysis,
                enhanced_system_prompt=enhanced_system_prompt
            )
        
        # 調用模型
        if BEDROCK_WEB_SEARCH and requires_web_search:
            response = invoke_bedrock_with_web_search(prompt, extract_search_query(message))
        else:
            response = invoke_bedrock(prompt)
        
        # 儲存對話歷史
        save_conversation(user_id, session_id, message, response)
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': 'https://d185h9ecahpj1h.cloudfront.net',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                'Access-Control-Allow-Methods': 'POST,OPTIONS'
            },
            'body': json.dumps({
                'response': response or "很抱歉，無法生成回應。請稍後再試。",
                'web_search_used': requires_web_search,
                'expertise_level': expertise_level  # 添加這行，返回專業度
            })
        }
    
    except Exception as e:
        print(f"Error: {str(e)}")
        traceback.print_exc()  # 打印詳細的錯誤堆疊
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': 'https://d185h9ecahpj1h.cloudfront.net',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                'Access-Control-Allow-Methods': 'POST,OPTIONS'
            },
            'body': json.dumps({
                'error': str(e),
                'trace': traceback.format_exc()
            })
        }

def analyze_file(file_key, file_type, file_content):
    """增強的文件分析功能，支持PDF、圖片和Excel等格式"""
    try:
        extracted_text = ""
        metadata = {}
        file_analysis_results = {
            "success": True,
            "file_type": file_type,
            "extracted_text": "",
            "structured_data": None,
            "tables": [],
            "entities": [],
            "key_phrases": []
        }
        
        # PDF文件處理
        if file_type == 'application/pdf':
            print(f"處理PDF文件: {file_key}")
            # 先將內容保存到臨時S3位置
            pdf_s3_key = file_key
            
            # 使用Textract同步API抽取文本
            response = textract.detect_document_text(
                Document={'S3Object': {'Bucket': 'stainless-steel-standards-docs', 'Name': pdf_s3_key}}
            )
            
            # 提取文本內容
            for item in response['Blocks']:
                if item['BlockType'] == 'LINE':
                    extracted_text += item['Text'] + "\n"
            
            # 如果PDF有多頁，可能需要啟動非同步作業
            if len(extracted_text) < 100:  # 如果提取的文本非常少，可能是多頁文檔
                print("使用非同步Textract作業處理多頁PDF")
                async_response = textract.start_document_text_detection(
                    DocumentLocation={'S3Object': {'Bucket': 'stainless-steel-standards-docs', 'Name': pdf_s3_key}}
                )
                job_id = async_response['JobId']
                
                # 這部分代碼實際上需要通過Step Functions或其他機制等待作業完成
                # 這裡僅做示例，實際實現時應考慮非同步處理流程
                print(f"Textract Job ID: {job_id} - 需要在生產環境中實現輪詢機制")
            
            # 嘗試提取表格
            try:
                tables_response = textract.analyze_document(
                    Document={'S3Object': {'Bucket': 'stainless-steel-standards-docs', 'Name': pdf_s3_key}},
                    FeatureTypes=['TABLES']
                )
                file_analysis_results["tables"] = extract_tables_from_textract(tables_response)
            except Exception as table_err:
                print(f"PDF表格提取錯誤: {str(table_err)}")
        
        # 圖片處理 (PNG, JPEG)
        elif file_type in ['image/png', 'image/jpeg', 'image/jpg']:
            print(f"處理圖片文件: {file_key}")
            
            # 使用Rekognition識別圖片中的文字
            response = rekognition.detect_text(
                Image={'Bytes': file_content}
            )
            
            detected_text = []
            for text in response['TextDetections']:
                if text['Type'] == 'LINE':
                    detected_text.append(text['DetectedText'])
                    extracted_text += text['DetectedText'] + "\n"
            
            file_analysis_results["detected_text_lines"] = detected_text
            
            # 使用Textract提取表格
            try:
                textract_response = textract.analyze_document(
                    Document={'Bytes': file_content},
                    FeatureTypes=['TABLES']
                )
                
                file_analysis_results["tables"] = extract_tables_from_textract(textract_response)
                
                # 如果Textract識別出表格，將表格數據添加到提取的文本中
                if file_analysis_results["tables"]:
                    extracted_text += "\n表格數據:\n"
                    for idx, table in enumerate(file_analysis_results["tables"]):
                        extracted_text += f"\n表格 {idx+1}:\n"
                        for row in table:
                            extracted_text += " | ".join(row) + "\n"
            except Exception as table_err:
                print(f"圖片表格識別錯誤: {str(table_err)}")
        
        # Excel文件處理
        elif file_type in ['application/vnd.ms-excel', 
                         'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet']:
            print(f"處理Excel文件: {file_key}")
            
            # 使用pandas讀取Excel
            excel_data = io.BytesIO(file_content)
            excel_file = pd.ExcelFile(excel_data)
            all_sheets = {}
            
            for sheet_name in excel_file.sheet_names:
                try:
                    df = pd.read_excel(excel_file, sheet_name=sheet_name)
                    
                    # 處理可能的NaN值
                    df = df.replace({np.nan: None})
                    
                    all_sheets[sheet_name] = df.to_dict(orient='records')
                    
                    # 將表格數據轉換為文本
                    extracted_text += f"\n工作表: {sheet_name}\n"
                    
                    # 添加列名
                    extracted_text += " | ".join(df.columns.astype(str)) + "\n"
                    extracted_text += "-" * 80 + "\n"
                    
                    # 添加值 (限制行數，避免文本過長)
                    max_rows = min(50, len(df))
                    for idx, row in df.head(max_rows).iterrows():
                        row_values = [str(v) if v is not None else "" for v in row.values]
                        extracted_text += " | ".join(row_values) + "\n"
                    
                    if len(df) > max_rows:
                        extracted_text += f"... 還有 {len(df) - max_rows} 行數據 ...\n"
                    
                    extracted_text += "\n"
                    
                except Exception as sheet_err:
                    print(f"處理工作表 '{sheet_name}' 時出錯: {str(sheet_err)}")
            
            # 保存結構化數據
            file_analysis_results["structured_data"] = all_sheets
        
        # CSV文件處理
        elif file_type == 'text/csv':
            print(f"處理CSV文件: {file_key}")
            
            try:
                # 讀取CSV並處理
                csv_data = io.BytesIO(file_content)
                df = pd.read_csv(csv_data)
                
                # 處理可能的NaN值
                df = df.replace({np.nan: None})
                
                # 將數據轉換為字典
                csv_records = df.to_dict(orient='records')
                file_analysis_results["structured_data"] = csv_records
                
                # 提取文本內容 (限制行數)
                extracted_text += "CSV數據:\n"
                
                # 添加列名
                extracted_text += " | ".join(df.columns.astype(str)) + "\n"
                extracted_text += "-" * 80 + "\n"
                
                # 添加值
                max_rows = min(50, len(df))
                for idx, row in df.head(max_rows).iterrows():
                    row_values = [str(v) if v is not None else "" for v in row.values]
                    extracted_text += " | ".join(row_values) + "\n"
                
                if len(df) > max_rows:
                    extracted_text += f"... 還有 {len(df) - max_rows} 行數據 ...\n"
            
            except Exception as csv_err:
                print(f"CSV處理錯誤: {str(csv_err)}")
                extracted_text += f"CSV解析失敗: {str(csv_err)}\n"
        
        # 純文本文件
        elif file_type in ['text/plain', 'application/txt']:
            print(f"處理文本文件: {file_key}")
            # 直接讀取文本
            extracted_text = file_content.decode('utf-8', errors='replace')
            
        else:
            print(f"未支持的文件類型: {file_type}")
            extracted_text = f"未支持的文件類型: {file_type}"
        
        # 儲存結果
        file_analysis_results["extracted_text"] = extracted_text
        
        # 如果提取的文本超過特定長度，進行實體識別和關鍵片語提取
        if len(extracted_text) > 50:
            try:
                # 選擇適當的語言
                language = 'zh' if contains_chinese(extracted_text) else 'en'
                
                # 提取實體 (如日期、數量等)
                if len(extracted_text) <= 5000:  # Comprehend有5KB的限制
                    entity_response = comprehend.detect_entities(
                        Text=extracted_text[:5000],
                        LanguageCode=language
                    )
                    file_analysis_results["entities"] = entity_response.get('Entities', [])
                
                # 提取關鍵片語
                if len(extracted_text) <= 5000:
                    key_phrases_response = comprehend.detect_key_phrases(
                        Text=extracted_text[:5000],
                        LanguageCode=language
                    )
                    file_analysis_results["key_phrases"] = key_phrases_response.get('KeyPhrases', [])
            except Exception as nlp_err:
                print(f"NLP處理錯誤: {str(nlp_err)}")
        
        # 將提取的文本保存到S3，方便後續查詢
        if extracted_text:
            text_key = f"{file_key}_extracted_text.txt"
            s3.put_object(
                Bucket='stainless-steel-standards-docs',
                Key=text_key,
                Body=extracted_text.encode('utf-8')
            )
            
            # 將文本提交到Kendra進行索引
            index_extracted_text(extracted_text, file_key)
        
        # 將分析結果保存為JSON
        analysis_result_key = f"{file_key}_analysis_result.json"
        clean_results = json.loads(json.dumps(file_analysis_results, default=str))
        
        s3.put_object(
            Bucket='stainless-steel-standards-docs',
            Key=analysis_result_key,
            Body=json.dumps(clean_results, ensure_ascii=False, indent=2).encode('utf-8'),
            ContentType='application/json'
        )
        
        print(f"文件分析完成: {file_key}")
        return clean_results
    
    except Exception as e:
        print(f"文件分析錯誤 {file_key}: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'file_type': file_type
        }

def extract_tables_from_textract(textract_response):
    """從Textract返回的表格結果中提取結構化數據"""
    tables = []
    
    if 'Blocks' not in textract_response:
        return tables
    
    # 找出所有表格
    table_blocks = {}
    cell_blocks = {}
    
    for block in textract_response['Blocks']:
        if block['BlockType'] == 'TABLE':
            table_blocks[block['Id']] = []
        elif block['BlockType'] == 'CELL':
            cell_blocks[block['Id']] = {
                'RowIndex': block['RowIndex'],
                'ColumnIndex': block['ColumnIndex'],
                'RowSpan': block.get('RowSpan', 1),
                'ColumnSpan': block.get('ColumnSpan', 1),
                'content': ''
            }
    
    # 找出所有單元格對應的表格
    for block in textract_response['Blocks']:
        if block['BlockType'] == 'TABLE' and 'Relationships' in block:
            for relationship in block['Relationships']:
                if relationship['Type'] == 'CHILD':
                    for cell_id in relationship['Ids']:
                        if cell_id in cell_blocks:
                            table_blocks[block['Id']].append(cell_id)
    
    # 填充單元格內容
    for block in textract_response['Blocks']:
        if block['BlockType'] == 'CELL' and 'Relationships' in block:
            cell_content = ''
            for relationship in block['Relationships']:
                if relationship['Type'] == 'CHILD':
                    for child_id in relationship['Ids']:
                        for content_block in textract_response['Blocks']:
                            if content_block['Id'] == child_id and content_block['BlockType'] in ['WORD', 'LINE']:
                                cell_content += content_block.get('Text', '') + ' '
            cell_blocks[block['Id']]['content'] = cell_content.strip()
    
    # 組織表格數據
    for table_id, cell_ids in table_blocks.items():
        if not cell_ids:
            continue
            
        # 確定表格大小
        max_row = 0
        max_col = 0
        for cell_id in cell_ids:
            cell = cell_blocks[cell_id]
            max_row = max(max_row, cell['RowIndex'])
            max_col = max(max_col, cell['ColumnIndex'])
        
        # 創建空表格
        table = [[''] * max_col for _ in range(max_row)]
        
        # 填充表格內容
        for cell_id in cell_ids:
            cell = cell_blocks[cell_id]
            row_idx = cell['RowIndex'] - 1  # 0-based index
            col_idx = cell['ColumnIndex'] - 1  # 0-based index
            table[row_idx][col_idx] = cell['content']
        
        tables.append(table)
    
    return tables

def index_extracted_text(text, source_key):
    """將提取的文本加入到Kendra索引中"""
    try:
        # 選擇適當的語言
        language = 'zh' if contains_chinese(text) else 'en'
        
        # 將文本切分成小塊，確保每塊不超過Kendra的限制
        max_chunk_size = 5000  # Kendra的文檔大小限制為5KB
        chunks = [text[i:i+max_chunk_size] for i in range(0, len(text), max_chunk_size)]
        
        for i, chunk in enumerate(chunks):
            chunk_id = f"extracted_{source_key.replace('/', '_')}_{i}"
            
            # 設置屬性過濾器的屬性
            attributes = {
                '_language_code': language,
                '_source_uri': f"s3://stainless-steel-standards-docs/{source_key}",
                '_file_type': 'PLAIN_TEXT'
            }
            
            # 創建屬性列表
            attribute_list = []
            for key, value in attributes.items():
                attribute_list.append({
                    'Key': key,
                    'Value': {'StringValue': value}
                })
            
            # 將文本塊加入Kendra索引
            response = kendra.batch_put_document(
                IndexId=KENDRA_INDEX_ID,
                Documents=[
                    {
                        'Id': chunk_id,
                        'Blob': chunk.encode('utf-8'),
                        'ContentType': 'PLAIN_TEXT',
                        'Title': f"從{source_key}提取的文本 (片段{i+1})",
                        'Attributes': attribute_list
                    }
                ]
            )
            print(f"已將文本片段{i+1}加入索引: {response}")
        
        return True
    except Exception as e:
        print(f"索引文本錯誤: {str(e)}")
        return False

def query_kendra(query):
    """查詢Kendra索引獲取相關知識"""
    try:
        response = kendra.query(
            IndexId=KENDRA_INDEX_ID,
            QueryText=query,
            AttributeFilter={
                "EqualsTo": {
                    "Key": "_language_code",
                    "Value": {
                        "StringValue": "zh" if contains_chinese(query) else "en"
                    }
                }
            }
        )
        
        # 提取搜索結果
        results = []
        for result in response['ResultItems']:
            document_title = result.get('DocumentTitle', {}).get('Text', '')
            document_excerpt = result.get('DocumentExcerpt', {}).get('Text', '')
            
            if document_excerpt:
                results.append({
                    'title': document_title,
                    'excerpt': document_excerpt,
                    'source': result.get('DocumentURI', '')
                })
        
        return results
    
    except Exception as e:
        print(f"Kendra query error: {str(e)}")
        return []

def contains_chinese(text):
    """檢查文本是否包含中文字符"""
    for char in text:
        if '\u4e00' <= char <= '\u9fff':
            return True
    return False

def get_conversation_history(user_id, session_id):
    """從DynamoDB獲取對話歷史"""
    try:
        response = conversation_table.query(
            KeyConditionExpression='user_id = :uid AND begins_with(timestamp_session, :sid)',
            ExpressionAttributeValues={
                ':uid': user_id,
                ':sid': f"{session_id}#"
            },
            ScanIndexForward=True,
            Limit=10  # 限制歷史記錄數量
        )
        
        history = []
        for item in response.get('Items', []):
            history.append({
                'role': 'human' if item['is_user'] else 'assistant',
                'content': item['message']
            })
        
        return history
    
    except Exception as e:
        print(f"Error retrieving conversation history: {str(e)}")
        return []

def save_conversation(user_id, session_id, user_message, assistant_response):
    """將對話儲存到DynamoDB"""
    import time
    
    timestamp = str(int(time.time() * 1000))
    
    # 保存用戶消息
    conversation_table.put_item(
        Item={
            'user_id': user_id,
            'timestamp_session': f"{session_id}#{timestamp}_1",
            'message': user_message,
            'is_user': True,
            'session_id': session_id,
            'timestamp': timestamp
        }
    )
    
    # 保存助理響應
    conversation_table.put_item(
        Item={
            'user_id': user_id,
            'timestamp_session': f"{session_id}#{timestamp}_2",
            'message': assistant_response,
            'is_user': False,
            'session_id': session_id,
            'timestamp': timestamp
        }
    )

def construct_prompt(message, conversation_history, kendra_results, file_content=None, file_type=None, file_key=None, extracted_text=None, enhanced_system_prompt=None, file_analysis=None):
    """使用增強的系統提示構建提示"""
    # 使用增強的系統提示或默認提示
    system_prompt = enhanced_system_prompt or """你是一個專業的不銹鋼國際規範AI助理，專門協助華新麗華公司的技術人員處理客戶訂單相關問題。
你擅長處理國際規範標準(ASTM、JIS、EN等)與規範項目(鋼種成分、尺寸公差、試驗標準等)的相關問題。
你需了解不同規範間的差異性，並能給予精確的回答。
當用戶上傳檔案時，你應分析其中內容並針對問題進行比對回答。
絕對不要向用戶請求提供額外資訊，如果不知道特定資訊，必須自行從已提供的資料中推斷或明確表示無法回答。
回答應包含充分的細節，並盡可能以表格形式呈現比較結果。
對比較結果要仔細計算化學成分區間，確保兩個標準的要求都能滿足。"""

    # 構建對話歷史
    conversation_text = ""
    for turn in conversation_history:
        role = "Human" if turn['role'] == 'human' else "Assistant"
        conversation_text += f"{role}: {turn['content']}\n\n"
    
    # 添加Kendra搜索結果作為背景知識
    knowledge_text = ""
    if kendra_results:
        knowledge_text = "以下是相關的專業知識參考:\n\n"
        for idx, result in enumerate(kendra_results):
            knowledge_text += f"參考 {idx+1}: {result['title']}\n"
            knowledge_text += f"{result['excerpt']}\n\n"
    
    if file_analysis is None:
        file_analysis = {}

    # 處理上傳的文件內容
    file_analysis_text = ""
    if file_content and file_type:
        file_analysis_text = "用戶已上傳文件，以下是文件分析結果:\n"
        
        # 添加文件類型信息
        file_analysis_text += f"文件類型: {file_type}\n"
        
        # 添加提取的文本內容
        if extracted_text:
            # 限制文本長度，避免提示過長
            max_text_length = 3000
            if len(extracted_text) > max_text_length:
                displayed_text = extracted_text[:max_text_length] + "...(內容已截斷)"
            else:
                displayed_text = extracted_text
                
            file_analysis_text += "提取的文本內容:\n"
            file_analysis_text += displayed_text + "\n\n"
        
        # 添加結構化數據信息
        if file_analysis and file_analysis.get('structured_data'):
            file_analysis_text += "檔案包含結構化數據。\n"
        
        # 添加表格信息
        if file_analysis and file_analysis.get('tables'):
            table_count = len(file_analysis.get('tables', []))
            file_analysis_text += f"檔案中識別出 {table_count} 個表格。\n"
        
        # 添加關鍵片語
        if file_analysis and file_analysis.get('key_phrases'):
            key_phrases = [phrase.get('Text', '') for phrase in file_analysis.get('key_phrases', [])[:10]]
            if key_phrases:
                file_analysis_text += "檔案關鍵片語: " + ", ".join(key_phrases) + "\n"
        
        # 添加實體識別結果
        if file_analysis and file_analysis.get('entities'):
            entities = {}
            for entity in file_analysis.get('entities', []):
                entity_type = entity.get('Type', '')
                entity_text = entity.get('Text', '')
                if entity_type not in entities:
                    entities[entity_type] = []
                if entity_text not in entities[entity_type]:
                    entities[entity_type].append(entity_text)
            
            if entities:
                file_analysis_text += "檔案中識別的實體:\n"
                for entity_type, texts in entities.items():
                    file_analysis_text += f"- {entity_type}: {', '.join(texts[:5])}"
                    if len(texts) > 5:
                        file_analysis_text += f" (還有 {len(texts)-5} 項)"
                    file_analysis_text += "\n"
        
        if file_key:
            file_analysis_text += f"文件已保存為: {file_key}\n"
    
    # 組合最終提示
    full_prompt = f"{system_prompt}\n\n"
    
    if knowledge_text:
        full_prompt += f"{knowledge_text}\n\n"
    
    if file_analysis_text:
        full_prompt += f"{file_analysis_text}\n\n"
    
    if conversation_text:
        full_prompt += f"{conversation_text}\n"
    
    full_prompt += f"Human: {message}\n\nAssistant:"
    
    return full_prompt

def construct_prompt_with_web_results(message, conversation_history, kendra_results, 
                                     web_results, detailed_content, 
                                     file_content=None, file_type=None, file_key=None,
                                     extracted_text=None, enhanced_system_prompt=None,
                                     file_analysis=None):
    """使用增強的系統提示構建網絡搜索提示"""
    # 使用增強的系統提示或默認提示
    system_prompt = enhanced_system_prompt or """你是一個專業的不銹鋼國際規範AI助理，專門協助華新麗華公司的技術人員處理客戶訂單相關問題。
你擅長處理國際規範標準(ASTM、JIS、EN等)與規範項目(鋼種成分、尺寸公差、試驗標準等)的相關問題。
你需了解不同規範間的差異性，並能給予精確的回答。
當用戶上傳檔案時，你應分析其中內容並針對問題進行比對回答。
絕對不要向用戶請求提供額外資訊，如果不知道特定資訊，必須自行從已提供的資料中推斷或明確表示無法回答。

為了提供最準確的信息，你已進行了網絡搜索獲取最新資料。在引用這些資料時，要清楚標明信息來源。
如果網絡搜索結果與內部知識庫有衝突，優先考慮最新的網絡搜索結果，特別是標準更新的情況。"""

    # 構建對話歷史
    conversation_text = ""
    for turn in conversation_history:
        role = "Human" if turn['role'] == 'human' else "Assistant"
        conversation_text += f"{role}: {turn['content']}\n\n"
    
    # 添加Kendra搜索結果
    knowledge_text = ""
    if kendra_results:
        knowledge_text = "以下是內部知識庫的相關專業知識參考:\n\n"
        for idx, result in enumerate(kendra_results):
            knowledge_text += f"內部參考 {idx+1}: {result['title']}\n"
            knowledge_text += f"{result['excerpt']}\n\n"
    
    if file_analysis is None:
        file_analysis = {}

    # 添加網絡搜索結果
    web_search_text = ""
    if web_results:
        web_search_text = "以下是從網絡搜索獲取的最新資料:\n\n"
        for idx, result in enumerate(web_results):
            web_search_text += f"網絡參考 {idx+1}: {result['title']}\n"
            web_search_text += f"來源: {result['link']}\n"
            web_search_text += f"摘要: {result['snippet']}\n\n"
    
    # 添加詳細網頁內容抓取結果
    detailed_content_text = ""
    if detailed_content:
        detailed_content_text = "以下是關鍵網頁的詳細內容:\n\n"
        for idx, content in enumerate(detailed_content):
            detailed_content_text += f"詳細內容 {idx+1}: {content['title']}\n"
            detailed_content_text += f"{content['content'][:1500]}...(內容已截斷)\n\n"
    
    # 處理上傳的文件內容
    file_analysis_text = ""
    if file_content and file_type:
        file_analysis_text = "用戶已上傳文件，以下是文件分析結果:\n"
        
        # 添加文件類型信息
        file_analysis_text += f"文件類型: {file_type}\n"
        
        # 添加提取的文本內容
        if extracted_text:
            # 限制文本長度，避免提示過長
            max_text_length = 3000
            if len(extracted_text) > max_text_length:
                displayed_text = extracted_text[:max_text_length] + "...(內容已截斷)"
            else:
                displayed_text = extracted_text
                
            file_analysis_text += "提取的文本內容:\n"
            file_analysis_text += displayed_text + "\n\n"
        
        # 添加結構化數據信息
        if file_analysis and file_analysis.get('structured_data'):
            file_analysis_text += "檔案包含結構化數據。\n"
        
        # 添加表格信息
        if file_analysis and file_analysis.get('tables'):
            table_count = len(file_analysis.get('tables', []))
            file_analysis_text += f"檔案中識別出 {table_count} 個表格。\n"
        
        if file_key:
            file_analysis_text += f"文件已保存為: {file_key}\n"
    
    # 組合最終提示
    full_prompt = f"{system_prompt}\n\n"
    
    if knowledge_text:
        full_prompt += f"{knowledge_text}\n\n"
    
    if web_search_text:
        full_prompt += f"{web_search_text}\n\n"
    
    if detailed_content_text:
        full_prompt += f"{detailed_content_text}\n\n"
    
    if file_analysis_text:
        full_prompt += f"{file_analysis_text}\n\n"
    
    if conversation_text:
        full_prompt += f"{conversation_text}\n"
    
    full_prompt += f"Human: {message}\n\nAssistant:"
    
    return full_prompt

def invoke_bedrock(prompt):
    """使用 modelId 調用 Bedrock（on-demand）"""
    try:
        final_reminder = "記住，不要向用戶請求提供額外資訊，使用現有資料作出最佳回答。"
        enhanced_prompt = prompt + "\n\n" + final_reminder
        
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4000,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}]
                }
            ],
            "temperature": 0.1,
            "top_p": 0.9,
            "top_k": 250
        }

        response = bedrock.invoke_model(
            modelId=os.environ.get("MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0"),
            body=json.dumps(request_body)
        )

        response_body = json.loads(response['body'].read())
        return response_body['content'][0]['text']

    except Exception as e:
        print(f"Error invoking Bedrock: {str(e)}")
        return f"Error: {str(e)}"

def invoke_bedrock_with_web_search(prompt, search_query):
    """使用網絡搜索功能調用Bedrock模型"""
    try:
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4000,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}]
                }
            ],
            "temperature": 0.1,
            "top_p": 0.9,
            "top_k": 250,
            "web_search": {
                "enable": True,
                "search_query": search_query
            }
        }

        response = bedrock.invoke_model(
            modelId=os.environ.get("MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0"),
            body=json.dumps(request_body)
        )

        response_body = json.loads(response['body'].read())
        return response_body['content'][0]['text']

    except Exception as e:
        print(f"Error invoking Bedrock: {str(e)}")
        return f"Error: {str(e)}"

def check_if_requires_web_search(message, kendra_results):
    """改進版：更積極地判斷是否需要進行網絡搜索，特別是針對標準查詢"""
    # 對於標準比較問題，始終進行網絡搜索
    standards_keywords = [
        "ASTM", "EN", "ISO", "JIS", "DIN", "UNS", "AISI", "SAE",
        "標準", "規範", "對應", "比較", "相當", "換算", "等同"
    ]
    
    for keyword in standards_keywords:
        if keyword in message:
            return True
    
    # 如果Kendra結果不足或可信度低
    if len(kendra_results) < 3:
        return True
    
    # 檢查Kendra結果是否提供足夠資訊
    has_comprehensive_info = False
    for result in kendra_results:
        if len(result.get('excerpt', '')) > 200:  # 如果有詳細的摘錄
            has_comprehensive_info = True
            break
    
    return not has_comprehensive_info

def extract_search_query(message):
    """從用戶消息中提取搜索查詢關鍵詞"""
    # 提取標準編號
    standard_patterns = [
        r'([A-Z]{2,5}\s*[A-Z]?[0-9]{1,5})',  # 匹配標準號，如ASTM A276
        r'([A-Z]{2,5}\s*[A-Z]?-[0-9]{1,5})'  # 匹配帶連字符的標準號
    ]
    
    standards = []
    for pattern in standard_patterns:
        matches = re.findall(pattern, message)
        standards.extend(matches)
    
    # 提取鋼種名稱
    steel_patterns = [
        r'([0-9]{1,3}-[0-9]{1,2}[A-Z]{1,2})',  # 如17-4PH
        r'(S[0-9]{5})',  # 如S32760
        r'(SUS\s*[0-9]{3})'  # 如SUS 630
    ]
    
    steels = []
    for pattern in steel_patterns:
        matches = re.findall(pattern, message)
        steels.extend(matches)
    
    # 組合搜索查詢
    search_terms = []
    
    if standards:
        search_terms.extend(standards)
    
    if steels:
        search_terms.extend(steels)
    
    # 添加"不銹鋼"和"標準"關鍵詞確保搜索結果相關
    search_query = " ".join(search_terms)
    if search_query:
        search_query += " 不銹鋼 標準 規範"
    else:
        # 如果沒有提取到特定標準或鋼種，使用整個消息作為查詢
        # 但限制長度並添加關鍵詞
        search_query = message[:100] + " 不銹鋼 標準 規範"
    
    return search_query

def web_search(query, api_key, search_engine_id):
    """使用Google Custom Search API搜索網絡"""
    if not api_key or not search_engine_id:
        print("Google API key or Search Engine ID not provided, skipping web search")
        return []
    
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        'key': api_key,
        'cx': search_engine_id,
        'q': query
    }
    
    try:
        response = requests.get(url, params=params)
        
        if response.status_code == 200:
            search_results = response.json()
            extracted_results = []
            
            for item in search_results.get('items', [])[:5]:  # 取前5個結果
                extracted_results.append({
                    'title': item.get('title', ''),
                    'link': item.get('link', ''),
                    'snippet': item.get('snippet', '')
                })
            
            return extracted_results
        else:
            print(f"Search API error: {response.status_code}, {response.text}")
            return []
    except Exception as e:
        print(f"Error in web search: {str(e)}")
        return []

def enhanced_web_search(query, api_key, search_engine_id):
    """增強的網絡搜索功能，特別針對鋼鐵標準比較進行優化"""
    results = []
    
    # 提取標準編號
    standard_pattern = r'(ASTM|EN|ISO|JIS|DIN|UNS|AISI|SAE)\s*[A-Z]?[0-9\-]+(?:[A-Z]+)?'
    standards = re.findall(standard_pattern, query)
    
    # 如果查詢包含鋼種比較，增加專業搜索詞
    if len(standards) >= 2 or ("對應" in query or "比較" in query or "相當" in query):
        enhanced_query = query + " 化學成分 對應標準 不銹鋼 規範比較"
        print(f"Enhanced steel standards query: {enhanced_query}")
    else:
        enhanced_query = query
    
    # 基本搜索
    google_results = web_search(enhanced_query, api_key, search_engine_id)
    results.extend(google_results)
    
    # 針對標準組織網站進行專門搜索
    standards_sites = [
        "astm.org", "en10088.info", "jisc.go.jp", "iso.org", 
        "steel-grades.com", "steel-standards.com", "totalmateria.com",
        "worldstainless.org", "steeldata.info"
    ]
    
    for site in standards_sites:
        site_query = f"{query} site:{site}"
        site_results = web_search(site_query, api_key, search_engine_id)
        for result in site_results:
            # 避免重複結果
            if not any(r['link'] == result['link'] for r in results):
                results.append(result)
    
    return results

def scrape_website(url):
    """增強版網頁抓取，針對鋼鐵標準網站優化"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # 移除不必要的元素
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.extract()
            
            # 特別關注表格內容（常包含化學成分）
            tables = soup.find_all('table')
            table_text = ""
            
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    row_text = ' | '.join([cell.get_text(strip=True) for cell in cells])
                    if row_text.strip():
                        table_text += row_text + "\n"
            
            # 提取正文文本
            paragraphs = soup.find_all('p')
            paragraph_text = "\n".join([p.get_text(strip=True) for p in paragraphs if p.get_text(strip=True)])
            
            # 組合所有文本
            text = ""
            if table_text:
                text += "表格數據:\n" + table_text + "\n\n"
            if paragraph_text:
                text += "網頁內容:\n" + paragraph_text
            
            # 如果沒有表格或段落，使用一般文本
            if not text:
                text = soup.get_text(separator='\n')
                lines = (line.strip() for line in text.splitlines())
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                text = '\n'.join(chunk for chunk in chunks if chunk)
            
            return text[:15000]  # 增加提取長度上限
        else:
            return f"無法抓取網頁，狀態碼: {response.status_code}"
    except Exception as e:
        return f"抓取網頁時出錯: {str(e)}"

def evaluate_user_expertise(message, conversation_history):
    """評估使用者在不銹鋼領域的專業程度，返回詳細分級結果"""
    # 初始化分數
    expertise_score = 0
    
    # 建立不同領域的專業術語詞庫
    metallurgy_terms = [
        "奧氏體", "肥粒體", "馬氏體", "沃斯田鐵", "δ-鐵素體", "肥粒體", "雙相", "析出硬化", 
        "時效硬化", "固溶處理", "再結晶", "晶粒", "晶界", "晶間腐蝕", "碳化物", "偏析",
        "塑性變形", "冷作硬化", "熱處理", "退火", "淬火", "回火", "固溶", "沉澱",
        "滲碳", "氮化", "σ相", "χ相", "金相", "位錯", "孿晶", "位錯", "晶格缺陷"
    ]
    
    corrosion_terms = [
        "點蝕", "縫隙腐蝕", "晶間腐蝕", "應力腐蝕開裂", "SCC", "氫脆", "電化學", 
        "陽極", "陰極", "鈍化", "活性", "氧化還原", "電位", "極化", "電流密度",
        "腐蝕電位", "電化學阻抗", "循環伏安", "PREN值", "CCT", "CPT", "IGC", "鹽霧測試"
    ]
    
    mechanical_terms = [
        "拉伸強度", "降伏強度", "屈服強度", "延伸率", "斷面收縮率", "彈性模量",
        "硬度", "洛氏硬度", "布氏硬度", "維氏硬度", "衝擊韌性", "疲勞強度", "蠕變",
        "斷裂韌性", "應力", "應變", "塑性", "脆性", "各向異性", "彈塑性", "應力集中"
    ]
    
    standards_terms = [
        "ASTM", "EN", "ISO", "JIS", "DIN", "UNS", "AISI", "SAE", "GB", "BS", 
        "符合性", "認證", "測試方法", "規格", "等級", "標準偏差", "公差"
    ]
    
    # 高級專業術語 - 這些詞語表示深度專業知識
    advanced_terms = [
        "PRE值計算", "Schaeffler圖", "DeLong圖", "WRC-1992", "孫能曲線", "Hall-Petch關係",
        "Thermo-Calc", "相圖計算", "電子背散射", "穿透式電子顯微鏡", "電化學阻抗譜", 
        "循環伏安法", "CALPHAD", "相場模型", "位錯動力學", "Gleeble", "等溫轉變",
        "連續冷卻轉變", "Z相", "Laves相", "組織定量分析", "晶粒尺寸分佈", "顯微硬度分析"
    ]
    
    # 專業問題類型模式
    comparison_pattern = r'(比較|差異|區別|對比|相比|優缺點|利弊|不同點)'
    calculation_pattern = r'(計算|公式|估算|轉換|換算|推導|求解)'
    mechanism_pattern = r'(機制|原理|機理|形成|過程|發展|演變|影響因素|條件)'
    standard_reference_pattern = r'[A-Z]{2,5}\s*[A-Z]?[0-9]{1,5}(-[0-9]+)?'
    composition_pattern = r'(C|Si|Mn|P|S|Cr|Ni|Mo|Ti|Nb|N|Cu|W|V|Co|Al)[<>=≤≥]?(\d+(\.\d+)?)(wt|%|質量分數)?'
    
    # 分析當前消息
    message_lower = message.lower()
    
    # 檢測各領域專業術語
    metallurgy_count = sum(1 for term in metallurgy_terms if term.lower() in message_lower)
    corrosion_count = sum(1 for term in corrosion_terms if term.lower() in message_lower)
    mechanical_count = sum(1 for term in mechanical_terms if term.lower() in message_lower)
    standards_count = sum(1 for term in standards_terms if term.lower() in message_lower)
    advanced_count = sum(1 for term in advanced_terms if term.lower() in message_lower)
    
    # 加權計算專業術語分數
    expertise_score += metallurgy_count * 1.0
    expertise_score += corrosion_count * 1.0
    expertise_score += mechanical_count * 1.0
    expertise_score += standards_count * 0.5
    expertise_score += advanced_count * 3.0  # 高級術語權重更高
    
    # 檢測問題類型的複雜度
    if re.search(comparison_pattern, message_lower):
        expertise_score += 1.5  # 比較分析表示一定的專業性
    
    if re.search(calculation_pattern, message_lower):
        expertise_score += 2.0  # 計算和公式表示較高專業性
    
    if re.search(mechanism_pattern, message_lower):
        expertise_score += 2.5  # 機制和原理探討表示高專業性
    
    # 檢測標準引用數量
    standard_refs = re.findall(standard_reference_pattern, message)
    expertise_score += len(standard_refs) * 1.5
    
    # 檢測化學成分表達式
    composition_refs = re.findall(composition_pattern, message)
    expertise_score += len(composition_refs) * 2.0
    
    # 句子結構複雜度分析
    sentences = re.split(r'[。！？.!?]', message)
    avg_sentence_length = sum(len(s) for s in sentences if s) / max(1, len([s for s in sentences if s]))
    if avg_sentence_length > 30:  # 長句可能表示更複雜的表達
        expertise_score += 1.0
    
    # 問句數量分析 - 多個問題可能表示更深入的探討
    question_count = message.count('?') + message.count('？')
    if question_count >= 3:
        expertise_score += 1.5
    
    # 分析歷史對話中的專業度
    history_expertise = 0
    if conversation_history:
        for turn in conversation_history[-5:]:  # 只看最近5次對話
            if turn['role'] == 'human':
                hist_message = turn['content'].lower()
                
                # 檢測各類專業術語
                hist_metallurgy = sum(1 for term in metallurgy_terms if term.lower() in hist_message)
                hist_corrosion = sum(1 for term in corrosion_terms if term.lower() in hist_message)
                hist_mechanical = sum(1 for term in mechanical_terms if term.lower() in hist_message)
                hist_standards = sum(1 for term in standards_terms if term.lower() in hist_message)
                hist_advanced = sum(1 for term in advanced_terms if term.lower() in hist_message)
                
                # 計算歷史專業度
                history_score = (hist_metallurgy + hist_corrosion + hist_mechanical) * 0.5
                history_score += hist_standards * 0.25
                history_score += hist_advanced * 1.5
                
                # 累加到歷史專業度
                history_expertise += history_score
    
    # 歷史專業度加權(但權重較低)
    expertise_score += history_expertise * 0.3
    
    # 確定最終專業等級
    # 將專業領域分布考慮進去
    domains_covered = sum(1 for count in [metallurgy_count, corrosion_count, mechanical_count, standards_count] if count > 0)
    
    # 根據分數和領域覆蓋確定專業等級
    if expertise_score >= 12 or (expertise_score >= 8 and domains_covered >= 3) or advanced_count >= 2:
        expertise_level = "expert"  # 專家級
        confidence = min(1.0, (expertise_score - 8) / 10)  # 信心度
    elif expertise_score >= 5 or (expertise_score >= 3 and domains_covered >= 2):
        expertise_level = "intermediate"  # 中級專業人士
        confidence = min(1.0, (expertise_score - 3) / 5)  # 信心度
    else:
        expertise_level = "beginner"  # 初學者或一般用戶
        confidence = min(1.0, expertise_score / 3)  # 信心度
    
    print(f"User expertise evaluation: score={expertise_score:.2f}, domains={domains_covered}, level={expertise_level}, confidence={confidence:.2f}")
    
    # 返回詳細評估結果
    return {
        "level": expertise_level,
        "score": expertise_score,
        "confidence": confidence,
        "domains": {
            "metallurgy": metallurgy_count,
            "corrosion": corrosion_count,
            "mechanical": mechanical_count,
            "standards": standards_count,
            "advanced": advanced_count
        },
        "domains_covered": domains_covered
    }

def internal_reasoning(message, conversation_history, knowledge_base, web_results=None, expertise_level="beginner"):
    """在返回最終答案前，進行多次內部推理以產生更高質量的回答"""
    
    # 構建初步思考提示
    reasoning_prompt = f"""為了生成高質量回答，我需要先進行一些內部推理。
問題：{message}

用戶專業水平：{expertise_level}

可用的知識：
{knowledge_base}

"""
    if web_results:
        reasoning_prompt += f"""
網絡搜索結果：
{web_results}

"""
    
    reasoning_prompt += """
#第一步：問題分析
- 用戶真正想知道的核心問題是什麼？
- 需要哪些關鍵信息來回答這個問題？
- 需要進行哪些計算或比較？

#第二步：資料評估
- 我有足夠的信息回答這個問題嗎？
- 哪些信息是最可靠的？
- 有沒有矛盾的信息需要解決？

#第三步：專業知識應用
- 應該應用哪些不銹鋼領域的專業知識？
- 需要參考哪些標準規範？
- 如何確保技術準確性？

#第四步：回答構思
- 如何根據用戶專業水平調整回答的深度和用詞？
- 如何組織信息，使回答清晰有條理？
- 需要使用表格、比較或列表嗎？

現在，基於以上思考，展開我的分析："""

    # 調用Bedrock進行第一輪內部推理
    first_reasoning = invoke_internal_reasoning(reasoning_prompt)
    
    # 構建第二輪思考，基於第一輪的結果
    second_prompt = f"""基於我的初步分析：

{first_reasoning}

我現在需要組織一個結構化的回答。考慮到用戶的專業水平是「{expertise_level}」，我應該：

1. 如果是初學者：提供基本解釋並解釋術語，避免過於技術性的細節
2. 如果是中級：提供更詳細的解釋，包括一些技術細節，但仍需附帶背景信息
3. 如果是專家：直接提供技術性資訊，可使用專業術語，重點關注數據和細節

現在，讓我生成最終回答的草稿："""

    # 調用Bedrock進行第二輪推理，生成回答草稿
    draft_response = invoke_internal_reasoning(second_prompt)
    
    # 最終審查和完善
    final_prompt = f"""這是我的回答草稿：

{draft_response}

讓我審查並完善這個回答：
1. 確保技術準確性
2. 確保信息組織清晰
3. 適當調整語言以匹配用戶專業水平（{expertise_level}）
4. 檢查是否有任何遺漏的重要信息
5. 確保沒有請求用戶提供更多信息

最終回答："""

    # 調用Bedrock進行最終完善
    final_response = invoke_internal_reasoning(final_prompt)
    
    return final_response

def invoke_internal_reasoning(prompt):
    """專門用於內部推理過程的Bedrock調用"""
    try:
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 4000,
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}]
                }
            ],
            "temperature": 0.2,  # 較低的溫度以獲得更一致的推理
            "top_p": 0.9,
            "top_k": 250
        }

        response = bedrock.invoke_model(
            modelId=os.environ.get("MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0"),
            body=json.dumps(request_body)
        )

        response_body = json.loads(response['body'].read())
        return response_body['content'][0]['text']

    except Exception as e:
        print(f"Error in internal reasoning: {str(e)}")
        return f"推理過程錯誤: {str(e)}"