/**
 * Frontend JavaScript cho LegalGuard AI Chatbot.
 * Xử lý Streaming Response (SSE), Quản lý Session NoSQL, và Tương tác UI.
 */

// ==========================================
// STATE MANAGEMENT
// ==========================================
const state = {
    userId: "user_demo",
    currentSessionId: null,
    sessions: [],
    isGenerating: false
};

// ==========================================
// DOM ELEMENTS
// ==========================================
const elements = {
    sidebar: document.getElementById("sidebar"),
    sidebarToggle: document.getElementById("sidebarToggle"),
    newChatBtn: document.getElementById("newChatBtn"),
    sessionList: document.getElementById("sessionList"),
    chatSessionTitle: document.getElementById("chatSessionTitle"),
    chatContainer: document.getElementById("chatContainer"),
    welcomeScreen: document.getElementById("welcomeScreen"),
    messagesList: document.getElementById("messagesList"),
    chatInput: document.getElementById("chatInput"),
    sendBtn: document.getElementById("sendBtn"),
    clearChatBtn: document.getElementById("clearChatBtn"),
    viewLogsBtn: document.getElementById("viewLogsBtn"),
    logsModal: document.getElementById("logsModal"),
    closeModalBtn: document.getElementById("closeModalBtn"),
    securityLogsTableBody: document.getElementById("securityLogsTableBody"),
    promptCards: document.querySelectorAll(".prompt-card")
};

// ==========================================
// INITIALIZATION
// ==========================================
document.addEventListener("DOMContentLoaded", () => {
    initApp();
});

async function initApp() {
    setupEventListeners();
    await loadSessions();
}

function setupEventListeners() {
    // Input & Send button
    elements.chatInput.addEventListener("input", handleInputChange);
    elements.chatInput.addEventListener("keydown", handleInputKeydown);
    elements.sendBtn.addEventListener("click", handleSendMessage);

    // New chat button
    elements.newChatBtn.addEventListener("click", () => startNewChat());

    // Sidebar Toggle (Mobile)
    elements.sidebarToggle.addEventListener("click", () => {
        elements.sidebar.classList.toggle("open");
    });

    // Clear chat button
    elements.clearChatBtn.addEventListener("click", handleDeleteCurrentSession);

    // Quick prompt cards
    elements.promptCards.forEach(card => {
        card.addEventListener("click", () => {
            const prompt = card.getAttribute("data-prompt");
            if (prompt) {
                elements.chatInput.value = prompt;
                handleInputChange();
                handleSendMessage();
            }
        });
    });

    // Security Logs Modal
    elements.viewLogsBtn.addEventListener("click", openSecurityLogsModal);
    elements.closeModalBtn.addEventListener("click", () => {
        elements.logsModal.classList.remove("active");
    });
    elements.logsModal.addEventListener("click", (e) => {
        if (e.target === elements.logsModal) {
            elements.logsModal.classList.remove("active");
        }
    });
}

function handleInputChange() {
    const text = elements.chatInput.value.trim();
    elements.sendBtn.disabled = text.length === 0 || state.isGenerating;

    // Auto resize textarea
    elements.chatInput.style.height = "auto";
    elements.chatInput.style.height = `${Math.min(elements.chatInput.scrollHeight, 160)}px`;
}

function handleInputKeydown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        if (!elements.sendBtn.disabled) {
            handleSendMessage();
        }
    }
}

// ==========================================
// SESSION MANAGEMENT (NoSQL Backend)
// ==========================================

async function loadSessions() {
    try {
        const res = await fetch(`/api/sessions?user_id=${state.userId}`);
        const data = await res.json();
        state.sessions = data.sessions || [];
        renderSessionList();

        if (state.sessions.length > 0) {
            // Load the most recent session
            await selectSession(state.sessions[0].session_id);
        } else {
            // Start a new session
            await startNewChat();
        }
    } catch (err) {
        console.error("Lỗi tải danh sách session:", err);
    }
}

function renderSessionList() {
    elements.sessionList.innerHTML = "";
    state.sessions.forEach(sess => {
        const item = document.createElement("div");
        item.className = `session-item ${sess.session_id === state.currentSessionId ? "active" : ""}`;
        item.innerHTML = `
            <i class="fa-regular fa-message"></i>
            <span class="session-title-text" title="${sess.title || 'Cuộc trò chuyện'}">${sess.title || "Cuộc trò chuyện mới"}</span>
            <button class="delete-session-btn" data-id="${sess.session_id}" title="Xóa">
                <i class="fa-solid fa-trash"></i>
            </button>
        `;

        item.addEventListener("click", (e) => {
            if (!e.target.closest(".delete-session-btn")) {
                selectSession(sess.session_id);
            }
        });

        const delBtn = item.querySelector(".delete-session-btn");
        delBtn.addEventListener("click", async (e) => {
            e.stopPropagation();
            await deleteSession(sess.session_id);
        });

        elements.sessionList.appendChild(item);
    });
}

async function selectSession(sessionId) {
    if (state.isGenerating) return;
    state.currentSessionId = sessionId;
    renderSessionList();

    try {
        const res = await fetch(`/api/sessions/${sessionId}?user_id=${state.userId}`);
        const data = await res.json();
        const session = data.session;

        if (session) {
            elements.chatSessionTitle.textContent = session.title || "Cuộc trò chuyện mới";
            renderMessages(session.messages || []);
        }
    } catch (err) {
        console.error("Lỗi lấy chi tiết session:", err);
    }
}

async function startNewChat() {
    if (state.isGenerating) return;
    try {
        const res = await fetch("/api/sessions", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ user_id: state.userId, title: "Cuộc trò chuyện mới" })
        });
        const data = await res.json();
        const newSession = data.session;

        state.sessions.unshift(newSession);
        state.currentSessionId = newSession.session_id;
        renderSessionList();

        elements.chatSessionTitle.textContent = newSession.title;
        renderMessages([]);
        elements.chatInput.focus();
    } catch (err) {
        console.error("Lỗi tạo session mới:", err);
    }
}

async function deleteSession(sessionId) {
    if (confirm("Bạn có chắc chắn muốn xóa đoạn chat này khỏi cơ sở dữ liệu không?")) {
        try {
            await fetch(`/api/sessions/${sessionId}?user_id=${state.userId}`, { method: "DELETE" });
            state.sessions = state.sessions.filter(s => s.session_id !== sessionId);
            if (state.currentSessionId === sessionId) {
                if (state.sessions.length > 0) {
                    await selectSession(state.sessions[0].session_id);
                } else {
                    await startNewChat();
                }
            } else {
                renderSessionList();
            }
        } catch (err) {
            console.error("Lỗi xóa session:", err);
        }
    }
}

async function handleDeleteCurrentSession() {
    if (state.currentSessionId) {
        await deleteSession(state.currentSessionId);
    }
}

// ==========================================
// MESSAGE RENDERING
// ==========================================

function renderMessages(messages) {
    elements.messagesList.innerHTML = "";

    if (!messages || messages.length === 0) {
        elements.welcomeScreen.style.display = "block";
        elements.messagesList.style.display = "none";
        return;
    }

    elements.welcomeScreen.style.display = "none";
    elements.messagesList.style.display = "flex";

    messages.forEach(msg => {
        appendMessageElement(msg.role, msg.content, msg.citations, msg.guard_meta);
    });

    scrollToBottom();
}

function appendMessageElement(role, content, citations = [], guardMeta = {}) {
    const row = document.createElement("div");
    row.className = `message-row ${role === "user" ? "user-row" : "bot-row"}`;

    const avatar = document.createElement("div");
    avatar.className = "message-avatar";
    avatar.innerHTML = role === "user" ? '<i class="fa-solid fa-user"></i>' : '<i class="fa-solid fa-scale-balanced"></i>';

    const contentDiv = document.createElement("div");
    contentDiv.className = "message-content";

    // Nếu bị chặn bởi Prompt Guard
    if (guardMeta && guardMeta.blocked) {
        const banner = document.createElement("div");
        banner.className = "guard-attack-banner";
        banner.innerHTML = `
            <i class="fa-solid fa-triangle-exclamation"></i>
            <div class="guard-attack-details">
                <h5>CẢNH BÁO: TẤN CÔNG BẢO MẬT ĐÃ BỊ CHẶN</h5>
                <p>Prompt Guard phát hiện quy tắc độc hại: <strong>${(guardMeta.rules || []).join(", ")}</strong>.</p>
            </div>
        `;
        contentDiv.appendChild(banner);
    }

    // Khung trích dẫn căn cứ pháp lý
    if (citations && citations.length > 0) {
        const citBox = document.createElement("div");
        citBox.className = "citations-box";
        citBox.innerHTML = `
            <div class="citations-header">
                <span><i class="fa-solid fa-book-bookmark"></i> ${citations.length} CĂN CỨ PHÁP LÝ SÁT NHẤT (RAG Grounding)</span>
                <i class="fa-solid fa-chevron-down"></i>
            </div>
            <div class="citations-list">
                ${citations.map(c => `
                    <div class="citation-item">
                        <div class="citation-title">
                            <span>${c.title} (${c.so_ky_hieu})</span>
                            <span class="citation-score">Độ khớp: ${(c.score * 100).toFixed(1)}%</span>
                        </div>
                        <div class="citation-snippet">${c.snippet}</div>
                    </div>
                `).join("")}
            </div>
        `;

        citBox.querySelector(".citations-header").addEventListener("click", () => {
            const list = citBox.querySelector(".citations-list");
            const icon = citBox.querySelector(".citations-header i.fa-chevron-down, .citations-header i.fa-chevron-up");
            if (list.style.display === "none") {
                list.style.display = "flex";
                icon.className = "fa-solid fa-chevron-down";
            } else {
                list.style.display = "none";
                icon.className = "fa-solid fa-chevron-up";
            }
        });

        contentDiv.appendChild(citBox);
    }

    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    bubble.innerHTML = marked.parse(content || "");
    contentDiv.appendChild(bubble);

    row.appendChild(avatar);
    row.appendChild(contentDiv);
    elements.messagesList.appendChild(row);

    return bubble;
}

function scrollToBottom() {
    elements.chatContainer.scrollTop = elements.chatContainer.scrollHeight;
}

// ==========================================
// STREAMING CHAT (Server-Sent Events)
// ==========================================

async function handleSendMessage() {
    const query = elements.chatInput.value.trim();
    if (!query || state.isGenerating) return;

    state.isGenerating = true;
    elements.chatInput.value = "";
    handleInputChange();

    // Ẩn welcome screen
    elements.welcomeScreen.style.display = "none";
    elements.messagesList.style.display = "flex";

    // Hiển thị tin nhắn của User
    appendMessageElement("user", query);
    scrollToBottom();

    // Tạo bubble cho Bot chuẩn bị stream
    const botRow = document.createElement("div");
    botRow.className = "message-row bot-row";
    botRow.innerHTML = `
        <div class="message-avatar"><i class="fa-solid fa-scale-balanced"></i></div>
        <div class="message-content">
            <div class="message-bubble"><i class="fa-solid fa-circle-notch fa-spin text-primary"></i> <em>Đang kiểm duyệt bảo mật & truy vấn điều luật...</em></div>
        </div>
    `;
    elements.messagesList.appendChild(botRow);
    scrollToBottom();

    const botBubble = botRow.querySelector(".message-bubble");
    const botContentDiv = botRow.querySelector(".message-content");

    let fullResponseText = "";
    let citationsData = [];

    try {
        const response = await fetch("/api/chat/stream", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                session_id: state.currentSessionId,
                user_id: state.userId,
                query: query
            })
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder("utf-8");
        let buffer = "";

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n\n");
            buffer = lines.pop(); // giữ lại phần dư

            for (const line of lines) {
                if (line.startsWith("data: ")) {
                    const eventData = JSON.parse(line.substring(6));

                    // 1. Guard check
                    if (eventData.type === "guard_result") {
                        if (!eventData.is_safe) {
                            botContentDiv.innerHTML = "";
                            const banner = document.createElement("div");
                            banner.className = "guard-attack-banner";
                            banner.innerHTML = `
                                <i class="fa-solid fa-triangle-exclamation"></i>
                                <div class="guard-attack-details">
                                    <h5>⛔ TẤN CÔNG ĐÃ BỊ CHẶN BỞI PROMPT GUARD</h5>
                                    <p>Quy tắc vi phạm: <strong>${eventData.matched_patterns.join(", ")}</strong> (Điểm rủi ro: ${eventData.risk_score})</p>
                                </div>
                            `;
                            botContentDiv.appendChild(banner);
                        }
                    }

                    // 2. Blocked message
                    else if (eventData.type === "blocked") {
                        const blockedBubble = document.createElement("div");
                        blockedBubble.className = "message-bubble";
                        blockedBubble.innerHTML = marked.parse(eventData.message);
                        botContentDiv.appendChild(blockedBubble);
                    }

                    // 3. Citations
                    else if (eventData.type === "citations") {
                        citationsData = eventData.citations;
                        if (citationsData.length > 0) {
                            const citBox = document.createElement("div");
                            citBox.className = "citations-box";
                            citBox.innerHTML = `
                                <div class="citations-header">
                                    <span><i class="fa-solid fa-book-bookmark"></i> ${citationsData.length} CĂN CỨ PHÁP LÝ SÁT NHẤT</span>
                                    <i class="fa-solid fa-chevron-down"></i>
                                </div>
                                <div class="citations-list">
                                    ${citationsData.map(c => `
                                        <div class="citation-item">
                                            <div class="citation-title">
                                                <span>${c.title} (${c.so_ky_hieu})</span>
                                                <span class="citation-score">${(c.score * 100).toFixed(1)}%</span>
                                            </div>
                                            <div class="citation-snippet">${c.snippet}</div>
                                        </div>
                                    `).join("")}
                                </div>
                            `;
                            botContentDiv.insertBefore(citBox, botBubble);
                        }
                        botBubble.innerHTML = ""; // Xóa spinner
                    }

                    // 4. Token Streaming
                    else if (eventData.type === "token") {
                        fullResponseText += eventData.token;
                        botBubble.innerHTML = marked.parse(fullResponseText);
                        scrollToBottom();
                    }

                    // 5. Done
                    else if (eventData.type === "done") {
                        // Cập nhật lại session title nếu cần
                        loadSessions();
                    }
                }
            }
        }
    } catch (err) {
        console.error("Lỗi khi stream câu trả lời:", err);
        botBubble.innerHTML = `<span class="text-danger"><i class="fa-solid fa-circle-exclamation"></i> Có lỗi xảy ra khi kết nối máy chủ: ${err.message}</span>`;
    } finally {
        state.isGenerating = false;
        handleInputChange();
    }
}

// ==========================================
// SECURITY AUDIT LOGS MODAL
// ==========================================

async function openSecurityLogsModal() {
    elements.logsModal.classList.add("active");
    elements.securityLogsTableBody.innerHTML = `<tr><td colspan="5" class="text-center"><i class="fa-solid fa-spinner fa-spin"></i> Đang tải dữ liệu...</td></tr>`;

    try {
        const res = await fetch("/api/security-logs?limit=30");
        const data = await res.json();
        const logs = data.logs || [];

        if (logs.length === 0) {
            elements.securityLogsTableBody.innerHTML = `<tr><td colspan="5" class="text-center text-muted">Chưa ghi nhận cuộc tấn công nào.</td></tr>`;
            return;
        }

        elements.securityLogsTableBody.innerHTML = logs.map(log => `
            <tr>
                <td><small>${log.timestamp}</small></td>
                <td><code>${escapeHtml(log.prompt)}</code></td>
                <td><span class="badge badge-warning">${(log.matched_rules || []).join(", ")}</span></td>
                <td><strong>${log.risk_score}</strong></td>
                <td><span class="badge badge-primary">${log.action}</span></td>
            </tr>
        `).join("");
    } catch (err) {
        elements.securityLogsTableBody.innerHTML = `<tr><td colspan="5" class="text-danger">Lỗi tải nhật ký bảo mật: ${err.message}</td></tr>`;
    }
}

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = text || "";
    return div.innerHTML;
}
