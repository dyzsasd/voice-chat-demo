// frontend/app.js

let socket = null;
let displayDiv = document.getElementById('transcript');
let serverAvailable = false;
let micAvailable = false;
let inputAudioContext = null;
let processor = null;
let globalStream = null;

let state = 'Idle';  // Possible states: 'Idle', 'Listening', 'Analysing', 'Playing'

// Get button elements
const startButton = document.getElementById('startButton');
const stopButton = document.getElementById('stopButton');

// Add event listeners to buttons
startButton.addEventListener('click', startChat);
stopButton.addEventListener('click', stopChat);

// Audio context for playing received audio data
let audioContext = null;

// Function to generate a simple UUID or random string as session_id
function generateSessionId() {
    return Math.random().toString(36);
}

function startChat() {
    // Create the AudioContext inside the user interaction
    audioContext = new (window.AudioContext || window.webkitAudioContext)();

    // Resume the AudioContext if it's in a suspended state
    if (audioContext.state === 'suspended') {
        audioContext.resume();
    }

    connectToServer();
    startRecording();
    startButton.disabled = true;
    stopButton.disabled = false;
    state = 'Listening';
    showRecordingAnimation();
}

function stopChat() {
    stopRecording();
    disconnectFromServer();
    startButton.disabled = false;
    stopButton.disabled = true;
    clearAnimation();
    state = 'Idle';

    // Close audio context and stop stream
    if (processor && inputAudioContext) {
        processor.disconnect();
        inputAudioContext.close();
        processor = null;
        inputAudioContext = null;
    }

    if (globalStream) {
        globalStream.getTracks().forEach(track => track.stop());
        globalStream = null;
    }
}

// Connect to the server
function connectToServer() {
    const sessionId = generateSessionId();
    socket = new WebSocket(`ws://localhost:8000/ws/${sessionId}`);

    // Set binary type to handle audio data
    socket.binaryType = 'arraybuffer';

    socket.onopen = function(event) {
        serverAvailable = true;
        console.log('WebSocket connection established');
    };

    socket.onmessage = function(event) {
        // Determine if the message is text
        if (typeof event.data === "string") {
            // It's a text message (probably JSON)
            let message = JSON.parse(event.data);
            if (message.type === "status") {
                if (message.value === "analysing") {
                    // Transition to Analysing state
                    state = 'Analysing';
                    // Show thinking animation
                    showThinkingAnimation();
                }
            } else if (message.type === "audio") {
                // Transition to Playing state
                state = 'Playing';
                // Clear any existing animations
                clearAnimation();
                // Decode base64 audio data and play it
                let audioData = base64ToArrayBuffer(message.value);
                playAudio(audioData);
            }
        } else {
            console.log("received unsupported event")
        }
    };

    socket.onclose = function(event) {
        serverAvailable = false;
        console.log('WebSocket connection closed');
    };

    socket.onerror = function(event) {
        console.error('WebSocket error:', event);
        serverAvailable = false;
    };
}

// Disconnect from the server
function disconnectFromServer() {
    if (socket) {
        socket.close();
        socket = null;
        serverAvailable = false;
    }
}

// Start recording and sending audio data
function startRecording() {
    navigator.mediaDevices.getUserMedia({ audio: true })
    .then(stream => {
        micAvailable = true;
        globalStream = stream;
        inputAudioContext = new (window.AudioContext || window.webkitAudioContext)();

        // Resume the inputAudioContext if it's in a suspended state
        if (inputAudioContext.state === 'suspended') {
            inputAudioContext.resume();
        }


        let source = inputAudioContext.createMediaStreamSource(stream);
        processor = inputAudioContext.createScriptProcessor(256, 1, 1);

        source.connect(processor);
        processor.connect(inputAudioContext.destination);

        processor.onaudioprocess = function(e) {
            if (state !== 'Listening') {
                return;
            }
            let inputData = e.inputBuffer.getChannelData(0);
            let outputData = new Int16Array(inputData.length);

            // Convert float audio data to 16-bit PCM
            for (let i = 0; i < inputData.length; i++) {
                let s = Math.max(-1, Math.min(1, inputData[i]));
                outputData[i] = s < 0 ? s * 0x8000 : s * 0x7FFF;
            }

            // Send 16-bit PCM data to server
            if (socket && socket.readyState === WebSocket.OPEN) {
                // Create JSON string with metadata
                let metadata = JSON.stringify({ sampleRate: inputAudioContext.sampleRate });
                // Convert metadata to byte array
                let metadataBytes = new TextEncoder().encode(metadata);
                // Create a buffer for metadata length (4 bytes, 32-bit integer)
                let metadataLength = new ArrayBuffer(4);
                let metadataLengthView = new DataView(metadataLength);
                // Set metadata length in the first 4 bytes
                metadataLengthView.setInt32(0, metadataBytes.byteLength, true); // Little endian

                // Combine metadata length, metadata, and audio data into one message
                let combinedData = new Blob([metadataLength, metadataBytes, outputData.buffer]);
                socket.send(combinedData);
            }
        };
    })
    .catch(e => {
        console.error('Cannot access microphone:', e);
        displayDiv.innerText = "🎤  Cannot access microphone  🎤";
    });
}

// Stop recording
function stopRecording() {
    if (processor && inputAudioContext) {
        processor.disconnect();
        inputAudioContext.close();
        processor = null;
        inputAudioContext = null;
    }

    if (globalStream) {
        // Stop all audio tracks
        globalStream.getTracks().forEach(track => track.stop());
        globalStream = null;
    }
}

// Play received audio data
function playAudio(arrayBuffer) {
    // Resume the AudioContext if it's in a suspended state
    if (audioContext.state === 'suspended') {
        audioContext.resume();
    }

    audioContext.decodeAudioData(arrayBuffer.slice(0), function(decodedData) {
        let source = audioContext.createBufferSource();
        source.buffer = decodedData;
        source.connect(audioContext.destination);
        source.start(0);
        source.onended = function() {
            // Audio playback finished
            // Transition back to Listening state
            state = 'Listening';
            showRecordingAnimation();
        };
    }, function(error) {
        console.error('Error decoding audio data', error);
    });
}

// Utility function to convert base64 to ArrayBuffer
function base64ToArrayBuffer(base64) {
    let binary_string = window.atob(base64);
    let len = binary_string.length;
    let bytes = new Uint8Array(len);
    for (let i = 0; i < len; i++) {
        bytes[i] = binary_string.charCodeAt(i);
    }
    return bytes.buffer;
}

// Show recording animation (wave animation)
function showRecordingAnimation() {
    let animationContainer = document.getElementById('animationContainer');
    animationContainer.innerHTML = '<div class="wave-animation"></div>';
}

// Show thinking animation (rotating circle)
function showThinkingAnimation() {
    let animationContainer = document.getElementById('animationContainer');
    animationContainer.innerHTML = '<div class="thinking-animation"></div>';
}

// Clear animations
function clearAnimation() {
    let animationContainer = document.getElementById('animationContainer');
    animationContainer.innerHTML = '';
}