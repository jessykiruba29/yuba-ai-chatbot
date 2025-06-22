import { useState } from "react";
import ChatWindow from './ChatWindow';
import './widget.css';

const Widget=(configuration,userEmail)=>{
    const[open,setopen]=useState(false);
    const handleClick=()=>{
        setopen(prev => !prev); //toggle
    }
    const closeChat=()=>{
        setopen(false);
    }
    return (
        <>
            <div className="icon">
                <button className="btn" onClick={handleClick}><img src="https://assets.onecompiler.app/42sryw8q2/42sryuhsc/qfojacpsckmlds-removebg-preview.png" alt="chat icon"></img></button>
            </div>

            {open && <ChatWindow closeChat={closeChat} userEmail={userEmail} configuration={configuration}/>}
        </>
    );
}
export default Widget;