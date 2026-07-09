// public/chatbot-widget.js
(function () {
  // Your backend API URL
  const API_URL = import.meta.env.VITE_PYTHON_API_URL || 'http://localhost:5054'; // Change to your FastAPI backend URL

  // Get shop domain
  const shop = window.Shopify?.shop || window.location.hostname;

  // Create widget HTML
  const widgetHTML = `
    <div id="shopify-chatbot" style="position:fixed; bottom:20px; right:20px; z-index:999999">
      <button id="chatbot-toggle" style="
        background:#008060;
        color:white;
        border:none;
        padding:12px 20px;
        border-radius:50px;
        cursor:pointer;
        font-size:16px;
        font-weight:bold;
        box-shadow:0 2px 10px rgba(0,0,0,0.2);
        display:flex;
        align-items:center;
        gap:8px
      ">
        💬 Chat with us
      </button>
      
      <div id="chatbot-window" style="
        display:none;
        position:absolute;
        bottom:70px;
        right:0;
        width:380px;
        height:500px;
        background:white;
        border-radius:12px;
        box-shadow:0 5px 20px rgba(0,0,0,0.15);
        border:1px solid #e0e0e0;
        flex-direction:column;
        overflow:hidden
      ">
        <div style="
          background:#008060;
          color:white;
          padding:15px;
          display:flex;
          justify-content:space-between;
          align-items:center
        ">
          <strong>AI Shopping Assistant</strong>
          <button id="chatbot-close" style="background:none; border:none; color:white; cursor:pointer; font-size:20px">×</button>
        </div>
        
        <div id="chatbot-messages" style="
          flex:1;
          padding:15px;
          overflow-y:auto;
          background:#f9f9f9
        "></div>
        
        <div style="padding:10px; border-top:1px solid #e0e0e0; display:flex; gap:8px">
          <input id="chatbot-input" type="text" placeholder="Ask about products..." style="
            flex:1;
            padding:10px;
            border:1px solid #ddd;
            border-radius:8px;
            outline:none
          ">
          <button id="chatbot-send" style="
            background:#008060;
            color:white;
            border:none;
            padding:10px 20px;
            border-radius:8px;
            cursor:pointer
          ">Send</button>
        </div>
      </div>
    </div>
  `;

  // Add to page
  document.body.insertAdjacentHTML('beforeend', widgetHTML);

  // Get elements
  const toggleBtn = document.getElementById('chatbot-toggle');
  const chatWindow = document.getElementById('chatbot-window');
  const closeBtn = document.getElementById('chatbot-close');
  const sendBtn = document.getElementById('chatbot-send');
  const input = document.getElementById('chatbot-input');
  const messagesDiv = document.getElementById('chatbot-messages');

  // Show greeting on first open
  let hasGreeting = false;

  toggleBtn.onclick = () => {
    const isHidden = chatWindow.style.display === 'none';
    chatWindow.style.display = isHidden ? 'flex' : 'none';
    if (isHidden && !hasGreeting) {
      addMessage('Hi! How can I help you find products today?', 'bot');
      hasGreeting = true;
    }
  };

  closeBtn.onclick = () => {
    chatWindow.style.display = 'none';
  };

  sendBtn.onclick = sendMessage;
  input.onkeypress = (e) => {
    if (e.key === 'Enter') sendMessage();
  };

  async function sendMessage() {
    const message = input.value.trim();
    if (!message) return;

    addMessage(message, 'user');
    input.value = '';

    // Show typing
    const typingId = showTyping();

    try {
      const response = await fetch(`${API_URL}/api/ai-search/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: message, shop: shop })
      });

      const data = await response.json();
      removeTyping(typingId);

      if (data.answer?.type === 'products' && data.answer.data) {
        showProducts(data.answer.message, data.answer.data);
      } else {
        addMessage(data.answer?.message || "No products found. Try a different search!", 'bot');
      }
    } catch (error) {
      removeTyping(typingId);
      addMessage('Sorry, having trouble connecting. Please try again.', 'bot');
    }
  }

  function addMessage(text, sender) {
    const msgDiv = document.createElement('div');
    msgDiv.style.cssText = `
      margin-bottom:12px;
      display:flex;
      justify-content:${sender === 'user' ? 'flex-end' : 'flex-start'}
    `;
    msgDiv.innerHTML = `
      <div style="
        max-width:80%;
        padding:8px 12px;
        border-radius:${sender === 'user' ? '15px 15px 0 15px' : '15px 15px 15px 0'};
        background:${sender === 'user' ? '#008060' : 'white'};
        color:${sender === 'user' ? 'white' : '#333'};
        box-shadow:0 1px 2px rgba(0,0,0,0.1)
      ">
        ${text}
      </div>
    `;
    messagesDiv.appendChild(msgDiv);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
  }

  function showProducts(message, products) {
    const container = document.createElement('div');
    container.style.cssText = 'margin-bottom:12px';

    let html = `
      <div style="background:white; border-radius:15px; padding:12px; box-shadow:0 1px 2px rgba(0,0,0,0.1)">
        <div style="margin-bottom:10px">${message}</div>
    `;

    products.slice(0, 5).forEach(product => {
      html += `
        <div onclick="selectProduct('${product.title}', ${product.price})" style="
          background:#f9f9f9;
          padding:10px;
          margin-bottom:8px;
          border-radius:8px;
          cursor:pointer;
          border:1px solid #e0e0e0
        ">
          <div style="font-weight:bold">${product.title}</div>
          <div style="color:#008060; margin-top:5px">$${product.price}</div>
        </div>
      `;
    });

    html += `</div>`;
    container.innerHTML = html;
    messagesDiv.appendChild(container);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;

    // Make function global
    window.selectProduct = async (title, price) => {
      addMessage(`Tell me about ${title}`, 'user');
      const typingId = showTyping();
      try {
        const response = await fetch(`${API_URL}/api/ai-search/`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: `Tell me about ${title}`, shop: shop })
        });
        const data = await response.json();
        removeTyping(typingId);
        addMessage(data.answer?.message || `${title} costs $${price}. Need more info?`, 'bot');
      } catch (error) {
        removeTyping(typingId);
        addMessage('Sorry, error fetching details.', 'bot');
      }
    };
  }

  function showTyping() {
    const id = 'typing-' + Date.now();
    const typingDiv = document.createElement('div');
    typingDiv.id = id;
    typingDiv.innerHTML = `
      <div style="background:white; border-radius:15px; padding:8px 12px; display:inline-block; box-shadow:0 1px 2px rgba(0,0,0,0.1)">
        Typing...
      </div>
    `;
    messagesDiv.appendChild(typingDiv);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
    return id;
  }

  function removeTyping(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
  }
})();