const API_BASE = window.location.origin;
let sessionId = localStorage.getItem('lenior_session') || null;
let messages = [];
let mediaRecorder = null;
let audioChunks = [];
let audioBlobURL = null;
let loading = false;

const chatArea = document.getElementById('chatArea');
const messagesContainer = document.getElementById('messagesContainer');
const typingIndicator = document.getElementById('typingIndicator');
const msgInput = document.getElementById('msgInput');
const sendBtn = document.getElementById('sendBtn');
const recordBtn = document.getElementById('recordBtn');
const stopBtn = document.getElementById('stopBtn');
const sendAudioBtn = document.getElementById('sendAudioBtn');
const cancelAudioBtn = document.getElementById('cancelAudioBtn');
const sessionDisplay = document.getElementById('sessionDisplay');

if (sessionId) sessionDisplay.textContent = `Sessão: ${sessionId.slice(0,12)}...`;

function scrollToBottom() {
    chatArea.scrollTop = chatArea.scrollHeight;
}

function renderMessages() {
    if (messages.length === 0) {
        messagesContainer.innerHTML = `
            <div class="empty-state">
                <p>🧠 Pergunte algo para Lenior</p>
                <p style="font-size:0.9rem;">Digite uma mensagem ou grave um áudio</p>
            </div>
        `;
        return;
    }
    let html = '';
    messages.forEach(msg => {
        const cls = msg.isUser ? 'user' : 'bot';
        html += `<div class="message ${cls}">${msg.text}</div>`;
    });
    messagesContainer.innerHTML = html;
    scrollToBottom();
}

async function sendMessage(text) {
    if (!text.trim() || loading) return;
    const userText = text.trim();
    messages.push({ text: userText, isUser: true });
    renderMessages();
    msgInput.value = '';
    loading = true;
    sendBtn.disabled = true;
    typingIndicator.style.display = 'flex';

    try {
        const payload = { texto: userText };
        if (sessionId) payload.sessao_id = sessionId;
        const res = await fetch(`${API_BASE}/chat/texto`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Erro desconhecido');
        const reply = data.resposta || 'Desculpe, não entendi.';
        if (data.sessao_id) {
            sessionId = data.sessao_id;
            localStorage.setItem('lenior_session', sessionId);
            sessionDisplay.textContent = `Sessão: ${sessionId.slice(0,12)}...`;
        }
        messages.push({ text: reply, isUser: false });
    } catch (err) {
        messages.push({ text: `❌ ${err.message}`, isUser: false });
    } finally {
        loading = false;
        sendBtn.disabled = false;
        typingIndicator.style.display = 'none';
        renderMessages();
    }
}

recordBtn.onclick = async () => {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];
        mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
        mediaRecorder.onstop = () => {
            const blob = new Blob(audioChunks, { type: 'audio/webm' });
            audioBlobURL = URL.createObjectURL(blob);
            stream.getTracks().forEach(t => t.stop());
            sendAudioBtn.style.display = 'inline-block';
            cancelAudioBtn.style.display = 'inline-block';
            recordBtn.style.display = 'none';
            stopBtn.style.display = 'none';
        };
        mediaRecorder.start();
        recordBtn.style.display = 'none';
        stopBtn.style.display = 'inline-block';
    } catch (e) {
        alert('Permissão do microfone negada.');
    }
};

stopBtn.onclick = () => {
    if (mediaRecorder && mediaRecorder.state === 'recording') {
        mediaRecorder.stop();
    }
};

cancelAudioBtn.onclick = () => {
    audioBlobURL = null;
    sendAudioBtn.style.display = 'none';
    cancelAudioBtn.style.display = 'none';
    recordBtn.style.display = 'inline-block';
    stopBtn.style.display = 'none';
};

sendAudioBtn.onclick = async () => {
    if (!audioBlobURL) return;
    const blob = await fetch(audioBlobURL).then(r => r.blob());
    const formData = new FormData();
    formData.append('audio', blob, 'recording.webm');
    if (sessionId) formData.append('sessao_id', sessionId);

    loading = true;
    sendBtn.disabled = true;
    typingIndicator.style.display = 'flex';
    messages.push({ text: '🎤 Enviei um áudio...', isUser: true });
    renderMessages();

    try {
        const res = await fetch(`${API_BASE}/chat/audio`, {
            method: 'POST',
            body: formData
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Erro no áudio');
        const reply = data.resposta || 'Áudio processado.';
        if (data.sessao_id) {
            sessionId = data.sessao_id;
            localStorage.setItem('lenior_session', sessionId);
            sessionDisplay.textContent = `Sessão: ${sessionId.slice(0,12)}...`;
        }
        messages.push({ text: reply, isUser: false });
    } catch (err) {
        messages.push({ text: `❌ ${err.message}`, isUser: false });
    } finally {
        loading = false;
        sendBtn.disabled = false;
        typingIndicator.style.display = 'none';
        renderMessages();
        sendAudioBtn.style.display = 'none';
        cancelAudioBtn.style.display = 'none';
        recordBtn.style.display = 'inline-block';
        stopBtn.style.display = 'none';
        audioBlobURL = null;
    }
};

sendBtn.onclick = () => sendMessage(msgInput.value);
msgInput.addEventListener('keypress', (e) => { if (e.key === 'Enter') sendMessage(msgInput.value); });

fetch(`${API_BASE}/status`).then(r => r.json()).then(data => {
    document.getElementById('statusText').textContent = `Online (${data.provedores.join(', ')})`;
}).catch(() => {
    document.getElementById('statusDot').textContent = '🔴';
    document.getElementById('statusText').textContent = 'Offline';
});

renderMessages();
