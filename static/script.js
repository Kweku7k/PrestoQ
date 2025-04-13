const chatBox = document.getElementById("chat-box");
const userInput = document.getElementById("user-input");
const budgetInput = document.getElementById("budget-input");

let sessionId = localStorage.getItem("sessionId") || crypto.randomUUID();
localStorage.setItem("sessionId", sessionId);

function appendMessage(role, text) {
    const message = document.createElement("div");
    message.textContent = `${role === "user" ? "🧍 You" : "🤖 AI"}: ${text}`;
    chatBox.appendChild(message);
    chatBox.scrollTop = chatBox.scrollHeight;
}

async function sendMessage() {
    const message = userInput.value.trim();
    const budget = budgetInput.value.trim();

    if (!message) return;

    appendMessage("user", message);
    userInput.value = "";

    const res = await fetch("/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            message,
            session_id: sessionId,
            budget: budget || null
        })
    });

    const data = await res.json();
    if (data.response) {
        appendMessage("ai", data.response);
    } else {
        appendMessage("ai", "Oops! Something went wrong.");
        console.error(data.error);
    }
}