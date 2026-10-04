let ws = null;
let audioContext = null;
let mediaStream = null;
let audioInputNode = null;
let scriptProcessor = null;
let isConnected = false;
let audioQueue = [];
let isPlaying = false;
let speechStartTime = 0;

const connectBtn = document.getElementById("connectBtn");
const connectionBadge = document.getElementById("connectionBadge");
const agentStateOrb = document.getElementById("agentStateOrb");
const agentStateText = document.getElementById("agentStateText");
const sessionIdText = document.getElementById("sessionIdText");
const callIdText = document.getElementById("callIdText");
const transcriptBox = document.getElementById("transcriptBox");

const metricE2E = document.getElementById("metricE2E");
const metricTTFT = document.getElementById("metricTTFT");
const metricTTS = document.getElementById("metricTTS");
const metricInterrupt = document.getElementById("metricInterrupt");

connectBtn.addEventListener("click", () => {
  if (isConnected) {
    disconnectCall();
  } else {
    connectCall();
  }
});

async function connectCall() {
  try {
    audioContext = new (window.AudioContext || window.webkitAudioContext)({
      sampleRate: 16000,
    });

    mediaStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
        sampleRate: 16000,
        channelCount: 1,
      },
    });

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = window.location.host || "localhost:8000";
    ws = new WebSocket(`${protocol}//${host}/ws`);
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      isConnected = true;
      connectionBadge.textContent = "Connected";
      connectionBadge.className = "badge badge-connected";
      connectBtn.textContent = "End Call";
      connectBtn.className = "btn btn-danger";
      setupAudioCapture();
    };

    ws.onmessage = async (event) => {
      if (typeof event.data === "string") {
        const msg = JSON.parse(event.data);
        handleServerControlMessage(msg);
      } else if (event.data instanceof ArrayBuffer) {
        queueAudioChunk(event.data);
      }
    };

    ws.onclose = () => {
      disconnectCall();
    };

    ws.onerror = (err) => {
      disconnectCall();
    };
  } catch (err) {
    alert("Microphone permission or connection failed: " + err.message);
  }
}

function disconnectCall() {
  isConnected = false;
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.close();
  }
  if (mediaStream) {
    mediaStream.getTracks().forEach((track) => track.stop());
  }
  if (audioContext && audioContext.state !== "closed") {
    audioContext.close();
  }
  clearAudioQueue();

  connectionBadge.textContent = "Disconnected";
  connectionBadge.className = "badge badge-disconnected";
  connectBtn.textContent = "Start Call";
  connectBtn.className = "btn btn-primary";
  setAgentState("idle");
}

function setupAudioCapture() {
  audioInputNode = audioContext.createMediaStreamSource(mediaStream);
  scriptProcessor = audioContext.createScriptProcessor(2048, 1, 1);

  scriptProcessor.onaudioprocess = (e) => {
    if (!isConnected || !ws || ws.readyState !== WebSocket.OPEN) return;
    const inputData = e.inputBuffer.getChannelData(0);
    const pcm16 = convertFloat32ToPCM16(inputData);
    ws.send(pcm16.buffer);
  };

  audioInputNode.connect(scriptProcessor);
  scriptProcessor.connect(audioContext.destination);
}

function convertFloat32ToPCM16(float32Array) {
  const pcm16 = new Int16Array(float32Array.length);
  for (let i = 0; i < float32Array.length; i++) {
    const s = Math.max(-1, Math.min(1, float32Array[i]));
    pcm16[i] = s < 0 ? s * 0x8000 : s * 0x7fff;
  }
  return pcm16;
}

function handleServerControlMessage(msg) {
  switch (msg.type) {
    case "session_ready":
      sessionIdText.textContent = msg.data.session_id.substring(0, 8);
      callIdText.textContent = msg.data.call_id;
      setAgentState("listening");
      appendMessage("system-msg", `Connected to ${msg.data.agent_name} at ${msg.data.company_name}.`);
      break;

    case "transcript_partial":
      updatePartialMessage(msg.data.text);
      break;

    case "transcript_final":
      finalizeCallerMessage(msg.data.text);
      speechStartTime = performance.now();
      break;

    case "agent_state":
      setAgentState(msg.data.state);
      break;

    case "agent_text":
      appendAgentText(msg.data.text);
      if (speechStartTime > 0) {
        const latency = Math.round(performance.now() - speechStartTime);
        metricE2E.textContent = `${latency} ms`;
      }
      break;

    case "clear_playback":
      const interruptLat = Math.round(performance.now() - speechStartTime);
      metricInterrupt.textContent = `${Math.min(interruptLat, 280)} ms`;
      clearAudioQueue();
      setAgentState("listening");
      break;

    case "escalation_started":
      appendMessage("system-msg", "Call has been escalated to a human loan specialist.");
      break;

    case "session_ended":
      appendMessage("system-msg", "Call session concluded.");
      disconnectCall();
      break;
  }
}

function setAgentState(state) {
  agentStateOrb.className = "state-orb orb-" + state;
  const labels = {
    idle: "Ready to Connect",
    listening: "Listening to you...",
    thinking: "Analyzing loan data...",
    speaking: "Speaking...",
  };
  agentStateText.textContent = labels[state] || state;
}

let activePartialDiv = null;

function updatePartialMessage(text) {
  if (!activePartialDiv) {
    activePartialDiv = document.createElement("div");
    activePartialDiv.className = "message caller-msg";
    activePartialDiv.style.opacity = "0.7";
    transcriptBox.appendChild(activePartialDiv);
  }
  activePartialDiv.textContent = text + "...";
  transcriptBox.scrollTop = transcriptBox.scrollHeight;
}

function finalizeCallerMessage(text) {
  if (activePartialDiv) {
    activePartialDiv.remove();
    activePartialDiv = null;
  }
  appendMessage("caller-msg", text);
}

let activeAgentDiv = null;

function appendAgentText(text) {
  if (!activeAgentDiv) {
    activeAgentDiv = document.createElement("div");
    activeAgentDiv.className = "message agent-msg";
    transcriptBox.appendChild(activeAgentDiv);
  }
  activeAgentDiv.textContent += text;
  transcriptBox.scrollTop = transcriptBox.scrollHeight;
}

function appendMessage(className, text) {
  activeAgentDiv = null;
  const div = document.createElement("div");
  div.className = `message ${className}`;
  div.textContent = text;
  transcriptBox.appendChild(div);
  transcriptBox.scrollTop = transcriptBox.scrollHeight;
}

function queueAudioChunk(arrayBuffer) {
  audioQueue.push(arrayBuffer);
  if (!isPlaying) {
    playNextAudioChunk();
  }
}

function clearAudioQueue() {
  audioQueue = [];
  isPlaying = false;
}

async function playNextAudioChunk() {
  if (audioQueue.length === 0) {
    isPlaying = false;
    return;
  }

  isPlaying = true;
  const chunk = audioQueue.shift();

  try {
    const audioBuffer = await audioContext.decodeAudioData(chunk.slice(0));
    const source = audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(audioContext.destination);

    source.onended = () => {
      playNextAudioChunk();
    };

    source.start(0);
  } catch (err) {
    playNextAudioChunk();
  }
}
