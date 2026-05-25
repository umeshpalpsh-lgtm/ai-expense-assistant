async function sendMessage() {
    const input = document.getElementById("user-input");
    const chatBox = document.getElementById("chat-box");

    const message = input.value.trim();

    if (!message) return;

    // user message
    const userDiv = document.createElement("div");
    userDiv.className = "user-message";
    userDiv.innerText = message;
    chatBox.appendChild(userDiv);

    input.value = "";

    // bot loading
    const botDiv = document.createElement("div");
    botDiv.className = "bot-message";
    botDiv.innerText = "Typing...";
    chatBox.appendChild(botDiv);

    chatBox.scrollTop = chatBox.scrollHeight;

    try {
        const response = await fetch("/chat", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                message: message
            })
        });

        const data = await response.json();
        botDiv.innerText = data.reply;
    } catch (error) {
        botDiv.innerText = "Server error. Dobara try karo.";
    }

    chatBox.scrollTop = chatBox.scrollHeight;
}

// Enter key support
document
    .getElementById("user-input")
    .addEventListener("keypress", function (e) {
        if (e.key === "Enter") {
            sendMessage();
        }
    });