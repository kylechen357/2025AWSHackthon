document.addEventListener('DOMContentLoaded', function() {
    console.log("Document loaded - initializing chat application");
    
    // 元素引用
    const chatBox = document.getElementById('chatBox');
    const messageInput = document.getElementById('messageInput');
    const sendButton = document.getElementById('sendButton');
    const fileInput = document.getElementById('fileInput');
    const clearFileBtn = document.getElementById('clearFileBtn');
    const uploadedFileInfo = document.getElementById('uploadedFileInfo');
    const loader = document.getElementById('loader');
    const webSearchIndicator = document.getElementById('webSearchIndicator');
    
    // API端點 - 部署後替換為實際API Gateway URL
    const API_ENDPOINT = 'https://9kv632fosa.execute-api.us-west-2.amazonaws.com/prod/assistant';
    
    // 用戶和會話ID
    const userId = 'user_' + Date.now();
    const sessionId = 'session_' + Date.now();
    console.log(`Session initialized: ${userId}, ${sessionId}`);
    
    // 事件監聽器
    sendButton.addEventListener('click', sendMessage);
    messageInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            sendMessage();
        }
    });
    
    fileInput.addEventListener('change', updateFileInfo);
    clearFileBtn.addEventListener('click', clearFileInput);
    
    // 根據專業度設置背景顏色 - 修改為更強制性的樣式應用
    function setBackgroundColorByExpertise(level) {
        console.log(`Setting background color for expertise level: "${level}"`);
        let color = '#f8f9fa'; // 預設顏色
        
        switch(level.toLowerCase()) {
            case 'beginner':
                color = '#edede9';
                console.log("Using beginner color");
                break;
            case 'intermediate':
                color = '#f5ebe0';
                console.log("Using intermediate color");
                break;
            case 'expert':
                color = '#d5bdaf';
                console.log("Using expert color");
                break;
            default:
                console.log("Using default color");
                color = '#f8f9fa';
        }
        
        console.log(`Applying background color: ${color}`);
        
        // 使用更強制性的方法確保樣式被應用
        document.body.style.backgroundColor = color;
        document.body.setAttribute('style', `background-color: ${color} !important`);
        
        // 添加CSS類來協助追蹤當前專業等級
        document.body.className = document.body.className.replace(/expertise-\w+/g, '');
        document.body.classList.add(`expertise-${level.toLowerCase()}`);
    }

    // 確保全局可訪問
    window.setBackgroundColorByExpertise = setBackgroundColorByExpertise;
    
    // 預設為初學者背景顏色
    console.log("Setting initial beginner background color");
    setBackgroundColorByExpertise('beginner');
    
    // 更新文件信息
    function updateFileInfo() {
        if (fileInput.files.length > 0) {
            const file = fileInput.files[0];
            uploadedFileInfo.textContent = `已選擇: ${file.name} (${formatFileSize(file.size)})`;
        } else {
            uploadedFileInfo.textContent = '';
        }
    }
    
    // 清除文件輸入
    function clearFileInput() {
        fileInput.value = '';
        uploadedFileInfo.textContent = '';
    }
    
    // 格式化文件大小
    function formatFileSize(bytes) {
        if (bytes < 1024) return bytes + ' bytes';
        else if (bytes < 1048576) return (bytes / 1024).toFixed(1) + ' KB';
        else if (bytes < 1073741824) return (bytes / 1048576).toFixed(1) + ' MB';
        else return (bytes / 1073741824).toFixed(1) + ' GB';
    }
  
    function addMessage(content, sender) {
        console.log(`Adding message from ${sender}`);
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${sender === 'user' ? 'user-message' : 'assistant-message'}`;
        
        if (sender === 'assistant') {
            // Check if content is defined and not null before parsing
            if (content && typeof content === 'string') {
                try {
                    messageDiv.innerHTML = marked.parse(content);
                } catch (error) {
                    console.error("Error parsing markdown:", error);
                    messageDiv.textContent = content; // Fallback to plain text
                }
            } else {
                console.error("Invalid content for marking:", content);
                messageDiv.textContent = "無法顯示回應內容";
            }
        } else {
            // User messages don't need markdown parsing
            messageDiv.textContent = content || "";
        }
        
        chatBox.appendChild(messageDiv);
        chatBox.scrollTop = chatBox.scrollHeight;
    }
    
    // 發送API請求
    function sendRequest(data) {
        console.log("Sending request to API:", data);
        fetch(API_ENDPOINT, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`網絡請求失敗: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log("Received raw API response:", data);
            
            // 隱藏載入動畫
            loader.style.display = 'none';
            
            // Extract the actual response text
            let responseText = null;
            let webSearchUsed = false;
            let expertiseLevel = 'beginner'; // 默認專業度
            
            if (data && typeof data === 'object') {
                // 嘗試從不同位置提取專業度 - 修改解析邏輯
                if (data.body && typeof data.body === 'string') {
                    try {
                        // Parse the nested response in the body (API Gateway format)
                        const parsedBody = JSON.parse(data.body);
                        console.log("Parsed body:", parsedBody);
                        responseText = parsedBody.response;
                        webSearchUsed = parsedBody.web_search_used || false;
                        
                        // 特別記錄專業度信息
                        expertiseLevel = parsedBody.expertise_level || 'beginner';
                        console.log("✓ Found expertise in parsed body:", expertiseLevel);
                    } catch (e) {
                        console.error("Failed to parse body:", e, data.body);
                    }
                } else if (data.response !== undefined) {
                    // Direct response format
                    responseText = data.response;
                    webSearchUsed = data.web_search_used || false;
                    expertiseLevel = data.expertise_level || 'beginner';
                    console.log("✓ Found expertise in direct format:", expertiseLevel);
                }
            }
            
            // 根據專業度設置背景顏色 - 確保在這裡調用，並使用實際收到的值
            console.log("Explicitly calling setBackgroundColorByExpertise with:", expertiseLevel);
            setTimeout(() => {
                // 使用setTimeout確保在DOM更新後應用樣式
                setBackgroundColorByExpertise(expertiseLevel);
                // 額外添加一個類來標記當前的專業度狀態，以便追蹤
                document.body.setAttribute('data-expertise', expertiseLevel);
            }, 10);
            
            // Ensure we have a valid string response
            if (!responseText || typeof responseText !== 'string') {
                console.error("Invalid response format:", data);
                responseText = "收到無效的回應格式，請稍後再試。";
            }
            
            // Add the response to the chat
            addMessage(responseText, 'assistant');
            
            // Show web search indicator if used
            if (webSearchUsed) {
                webSearchIndicator.style.display = 'block';
                setTimeout(() => {
                    webSearchIndicator.style.display = 'none';
                }, 5000);
            }
        })
        .catch(error => {
            // 隱藏載入動畫
            loader.style.display = 'none';
            
            // 顯示錯誤消息
            console.error('Request error:', error);
            addMessage(`發生錯誤: ${error.message}`, 'assistant');
        });
    }
    
    // 發送消息
    function sendMessage() {
        const message = messageInput.value.trim();
        if (!message && (!fileInput.files || fileInput.files.length === 0)) {
            return;
        }
        
        console.log("Sending message:", message);
        
        // 添加用戶消息到聊天框
        addMessage(message, 'user');
        
        // 清空輸入框
        messageInput.value = '';
        
        // 顯示載入動畫
        loader.style.display = 'block';
        
        // 隱藏網絡搜索指示器
        webSearchIndicator.style.display = 'none';
        
        // 準備請求數據
        const requestData = {
            user_id: userId,
            session_id: sessionId,
            message: message
        };
        
        // 如果有文件，添加到請求中
        if (fileInput.files && fileInput.files.length > 0) {
            const file = fileInput.files[0];
            const reader = new FileReader();
            
            reader.onload = function(e) {
                // 將文件內容轉為Base64
                const base64Content = e.target.result.split(',')[1];
                
                requestData.file = {
                    name: file.name,
                    type: file.type,
                    content: base64Content
                };

                //顯示上傳檔案
                addMessage(`📄 已上傳檔案：${file.name} (${formatFileSize(file.size)})`, 'user');
                
                // 發送請求
                sendRequest(requestData);
            };
            
            console.log("Reading file as DataURL");
            // 讀取文件為DataURL
            reader.readAsDataURL(file);
            clearFileInput();
        } else {
            // 無文件直接發送請求
            sendRequest(requestData);
        }
    }
  
    // 初始問候消息 (已在HTML中添加)
    console.log("Chat application initialization completed");
    
    // 添加調試按鈕事件處理器，確保它們可以正常工作
    const testButtons = document.querySelectorAll('.btn-outline-secondary');
    testButtons.forEach(button => {
        button.addEventListener('click', function() {
            console.log('Test button clicked');
            // 按鈕本身已有 onclick 屬性，但這裡添加額外的日誌
        });
    });
});