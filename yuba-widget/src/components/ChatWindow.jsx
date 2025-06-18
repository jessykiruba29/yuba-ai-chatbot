import { useEffect, useState,useRef} from "react";
import './widget.css';
import axios from 'axios';
import { FiMic } from "react-icons/fi";

const ChatWindow = ({ closeChat,userEmail,configuration }) => {
    const [message, setMessage] = useState('');
    const [history, setHistory] = useState([]);
    const chatEndRef = useRef(null); //scroll eff

    const [isListening, setIsListening] = useState(false);

const startListening = () => {
  if (!('webkitSpeechRecognition' in window)) {
    alert('Speech recognition not supported in this browser.');
    return;
  }

  const recognition = new window.webkitSpeechRecognition();
  recognition.continuous = false;
  recognition.lang = 'en-US';
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;

  recognition.onstart = () => {
    setIsListening(true);
    console.log("Listening...");
  };

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    console.log("Transcript:", transcript);
    setMessage(prev => prev + transcript); // Appends transcript to input
    setIsListening(false);
  };

  recognition.onerror = (event) => {
    console.error("Speech recognition error:", event.error);
    setIsListening(false);
  };

  recognition.onend = () => {
    setIsListening(false);
  };

  recognition.start();
};


     useEffect(()=>{
        chatEndRef.current?.scrollIntoView({behavior:"smooth"}); //for automatic scrolling to recent when new messages come
     },[history]);
    
    const handleChange = (e) => {
        setMessage(e.target.value);
    }

    const handleKeyPress=(e)=>{
        if(e.key==='Enter'){
            handleSend();
        }
    }

const handleSend = async () => {
    if (message.trim() === '') return;

    const user_msg = { text: message, sender: 'user' };
    setHistory(prev => [...prev, user_msg]);
    setMessage('');

    setHistory(prev => [...prev, { text: "Typing...", sender: 'bot', temp: true }]);

    try {
        console.log("Sending to backend:", {
            message: message,
            config_url: configuration,
        });

        const response = await axios.post(`${import.meta.env.VITE_BACKEND}/chat`, {
            message: message,
            config_url: configuration,
        },
    {
  withCredentials: true 
});

        setHistory(prev => prev.filter(msg => !msg.temp)); 

        
        if (response.data?.callback && window.chatbotCallback) {
            const { action, payload } = response.data.callback;
            try {
                const result = await window.chatbotCallback(action, payload);

                
                const formattingResponse = await axios.post(`${import.meta.env.VITE_BACKEND}/format`, {
                    raw_data: result,
                    org_msg: message,
                },
            {
  withCredentials: true 
});

                const formatted = formattingResponse.data.response || formattingResponse.data;

                setHistory(prev => [...prev, {
                    text: typeof formatted === "string" ? formatted : JSON.stringify(formatted, null, 2),
                    sender: 'bot'
                }]);

                return;
            } catch (callbackErr) {
                console.error("Callback error:", callbackErr);
                setHistory(prev => [...prev, {
                    text: "❌ Hmm, I couldn’t complete that request. Maybe the server is down or something went wrong.",
                    sender: 'bot'
                }]);
                return;
            }
        }

        
       
let botText = '';

if (response.data?.callback) {
  
} else if (typeof response.data === 'object' && 'response' in response.data) {
  
  botText = response.data.response;
} else if (typeof response.data === 'string') {
  botText = response.data.trim();
} else {
  botText = JSON.stringify(response.data, null, 2);
}

        setHistory(prev => [...prev, { text: botText, sender: 'bot' }]);

    } catch (error) {
        setHistory(prev => prev.filter(msg => !msg.temp));

        console.error("Error receiving response from AI", error);

        if (error.response) {
            console.error("Server responded with:", error.response.data);
        } else if (error.request) {
            console.error("No response received. Request was:", error.request);
        } else {
            console.error("Error setting up the request:", error.message);
        }

        setHistory(prev => [...prev, {
            text: "⚠️ Sorry, I couldn’t process that. Please try again or rephrase your request.",
            sender: 'bot'
        }]);
    }
};



    
    return (
        <div className="window">
            <div className="header">
                <h2>Yuba</h2>
                <button onClick={closeChat}>x</button>
            </div>
            <h3>Your Ultimate Backend Agent</h3>
            <div className="chat_area">
                {history.map((msg, idx) => (
                    <div key={idx} className={`message ${msg.sender}`}>
                        <strong>{msg.sender === 'user' ? 'You: ' : 'Bot: '}</strong>
                        {msg.text}
                    </div>
                ))}
                <div ref={chatEndRef}/>
            </div>
            <div className="input-wrapper">
  <div className="input-with-mic">
    <input
      type="text"
      value={message}
      onChange={handleChange}
      placeholder="Type your message..."
      onKeyDown={handleKeyPress}
    />
    <button
      onClick={startListening}
      className={`mic-inside ${isListening ? 'listening' : ''}`}
    >
      <FiMic />
    </button>
  </div>

  <button onClick={handleSend} className="bt">Send</button>
</div>
        </div>
    );
}

export default ChatWindow;