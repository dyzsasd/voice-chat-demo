// frontend/app.js

let socket = null;
let displayDiv = document.getElementById('transcript');
let serverAvailable = false;
let micAvailable = false;
let inputAudioContext = null;
let processor = null;
let globalStream = null;

// 获取按钮元素
const startButton = document.getElementById('startButton');
const stopButton = document.getElementById('stopButton');

// 为按钮添加事件监听器
startButton.addEventListener('click', startChat);
stopButton.addEventListener('click', stopChat);

// 播放接收到的音频数据
let audioContext = new (window.AudioContext || window.webkitAudioContext)();

function generateSessionId() {
    // 生成简单的UUID或随机字符串作为session_id
    return Math.random().toString(36).substr(2, 9);
}

function startChat() {
    connectToServer();
    startRecording();
    startButton.disabled = true;
    stopButton.disabled = false;
}

function stopChat() {
    stopRecording();
    disconnectFromServer();
    startButton.disabled = false;
    stopButton.disabled = true;
}

// 连接到服务器
function connectToServer() {
    const sessionId = generateSessionId();
    socket = new WebSocket(`ws://localhost:8000/ws/${sessionId}`);

    // 设置 WebSocket 的二进制类型为 ArrayBuffer，以处理音频数据
    socket.binaryType = 'arraybuffer';

    socket.onopen = function(event) {
        serverAvailable = true;
        console.log('WebSocket 连接已建立');
    };

    socket.onmessage = function(event) {
        // 从后端接收音频数据，播放音频
        console.log("get msg from bff")
        playAudio(event.data);
    };

    socket.onclose = function(event) {
        serverAvailable = false;
        console.log('WebSocket 连接已关闭');
    };

    socket.onerror = function(event) {
        console.error('WebSocket 错误：', event);
        serverAvailable = false;
    };
}

// 断开与服务器的连接
function disconnectFromServer() {
    if (socket) {
        socket.close();
        socket = null;
        serverAvailable = false;
    }
}

// 开始录音并发送音频数据
function startRecording() {
    navigator.mediaDevices.getUserMedia({ audio: true })
    .then(stream => {
        micAvailable = true;
        globalStream = stream;
        inputAudioContext = new (window.AudioContext || window.webkitAudioContext)();
        let source = inputAudioContext.createMediaStreamSource(stream);
        processor = inputAudioContext.createScriptProcessor(256, 1, 1);

        source.connect(processor);
        processor.connect(inputAudioContext.destination);

        processor.onaudioprocess = function(e) {
            let inputData = e.inputBuffer.getChannelData(0);
            let outputData = new Int16Array(inputData.length);

            // 将浮点音频数据转换为16位PCM格式
            for (let i = 0; i < inputData.length; i++) {
                let s = Math.max(-1, Math.min(1, inputData[i]));
                outputData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }

            // 发送16位PCM数据到服务器
            if (socket && socket.readyState === WebSocket.OPEN) {
                // 创建包含元数据的JSON字符串
                let metadata = JSON.stringify({ sampleRate: inputAudioContext.sampleRate });
                // 将元数据转换为字节数组
                let metadataBytes = new TextEncoder().encode(metadata);
                // 创建一个用于元数据长度的缓冲区（4字节，32位整数）
                let metadataLength = new ArrayBuffer(4);
                let metadataLengthView = new DataView(metadataLength);
                // 在前4个字节中设置元数据的长度
                metadataLengthView.setInt32(0, metadataBytes.byteLength, true); // 小端字节序

                // 将元数据长度、元数据和音频数据组合成一个消息
                let combinedData = new Blob([metadataLength, metadataBytes, outputData.buffer]);
                socket.send(combinedData);
            }
        };
    })
    .catch(e => {
        console.error('无法访问麦克风：', e);
        displayDiv.innerText = "🎤  无法访问麦克风  🎤";
    });
}

// 停止录音
function stopRecording() {
    if (processor && inputAudioContext) {
        processor.disconnect();
        inputAudioContext.close();
        processor = null;
        inputAudioContext = null;
    }

    if (globalStream) {
        // 停止所有音轨
        globalStream.getTracks().forEach(track => track.stop());
        globalStream = null;
    }
}

// 播放音频
function playAudio(arrayBuffer) {
    audioContext.decodeAudioData(arrayBuffer.slice(0), function(decodedData) {
        let source = audioContext.createBufferSource();
        source.buffer = decodedData;
        source.connect(audioContext.destination);
        source.start(0);
    }, function(error) {
        console.error('解码音频数据时出错', error);
    });
}