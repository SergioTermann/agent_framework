var S=Object.defineProperty;var M=(n,s,e)=>s in n?S(n,s,{enumerable:!0,configurable:!0,writable:!0,value:e}):n[s]=e;var p=(n,s,e)=>M(n,typeof s!="symbol"?s+"":s,e);import{r as A}from"./@vue-hjwuK2GK.js";function k(){const n=A([]);function s(){const i=localStorage.getItem("aiChatMessages");if(i)try{n.value=JSON.parse(i)}catch(u){console.error("Failed to load AI chat messages:",u),n.value=[]}}function e(){try{localStorage.setItem("aiChatMessages",JSON.stringify(n.value))}catch(i){console.error("Failed to save AI chat messages:",i)}}function a(i){n.value.push(i),e()}function l(i){if(n.value.length>0){const u=n.value[n.value.length-1];u.type==="bot"&&(u.text=i,e())}}function c(){n.value=[],localStorage.removeItem("aiChatMessages")}return s(),{aiMessages:n,addMessage:a,updateLastMessage:l,clearMessages:c,loadMessages:s,saveMessages:e}}const C=k();function b(){return C}const P="",D="http://localhost:2080";class R{constructor(s,e=D){p(this,"apiKey");p(this,"apiUrl");p(this,"conversationId",null);this.apiKey=s,this.apiUrl=e}async sendMessage(s,e="default-user",a){var u;const l={inputs:{},query:s,response_mode:"blocking",user:e},c=a||this.conversationId;c&&(l.conversation_id=c);const i={"Content-Type":"application/json",Authorization:`Bearer ${this.apiKey}`};try{const f=`${this.apiUrl}/chat-messages`,d=await fetch(f,{method:"POST",headers:i,body:JSON.stringify(l)});if(!d.ok){const g=await d.text();return console.error("Dify API 错误:",d.status),this.getMockResponse(s)}const t=await d.json();let r="";return t.message&&t.message.content?r=t.message.content:t.message&&t.message.answer?r=t.message.answer:t.answer?r=t.answer:t.result?r=t.result:t.data&&t.data.outputs?r=t.data.outputs.text||t.data.outputs.answer||t.data.outputs.result||"":t.outputs?r=t.outputs.text||t.outputs.answer||t.outputs.result||"":r="抱歉，我没有理解您的问题。",r||(r="抱歉，我没有理解您的问题。"),t.conversation_id&&(this.conversationId=t.conversation_id),{answer:r,conversation_id:t.conversation_id,message_id:t.message_id||((u=t.message)==null?void 0:u.id)}}catch(f){return console.error("Dify API 调用失败:",f),this.getMockResponse(s)}}getMockResponse(s){const e=s.toLowerCase();let a="";return e.includes("故障")||e.includes("告警")||e.includes("异常")?a=`我已经检测到系统中有告警信息。根据当前数据，白城风场有2台风机出现告警状态（白城-01和白城-04）。建议您：

1. 查看详细的故障日志
2. 检查风机的运行参数
3. 如有必要，安排现场检修

需要我提供更详细的故障分析吗？`:e.includes("风场")||e.includes("风机")?a=`当前系统监控着5个风场，共25台风机：

• 长岭风场：8台风机，运行正常
• 白城风场：6台风机，2台告警
• 通榆风场：5台风机，运行正常
• 洮南风场：4台风机，运行正常
• 镇赉风场：2台风机，运行正常

总装机容量：62.5MW

您想了解哪个风场的详细信息？`:e.includes("数据")||e.includes("报告")?a=`我可以为您提供以下数据报告：

• 实时运行数据
• 发电量统计
• 故障记录分析
• 维护保养记录

请告诉我您需要哪方面的数据？`:e.includes("你好")||e.includes("您好")||e.includes("hi")||e.includes("hello")?a=`您好！我是风起时域科技有限公司AI故障定位系统的智能助手。我可以帮您：

• 查询风场和风机运行状态
• 分析故障和告警信息
• 提供维护建议
• 生成数据报告

请问有什么可以帮您的吗？`:a=`我理解您的问题是关于"${s}"。作为AI助手，我可以帮您分析风场运行数据、诊断设备故障、提供维护建议等。

当前系统状态：
• 在线风机：25台
• 告警设备：2台
• 系统运行正常

您还想了解什么信息？`,{answer:a,conversation_id:"mock-conversation-"+Date.now(),message_id:"mock-message-"+Date.now()}}async sendMessageStream(s,e="default-user",a,l){var i,u;let c="";try{const f=`${this.apiUrl}/chat-messages`,d={inputs:{},query:s,response_mode:"streaming",user:e},t=l||this.conversationId;t&&(d.conversation_id=t);const r=await fetch(f,{method:"POST",headers:{Authorization:`Bearer ${this.apiKey}`,"Content-Type":"application/json"},body:JSON.stringify(d)});if(!r.ok)throw new Error(`Dify API error: ${r.status}`);const g=(i=r.body)==null?void 0:i.getReader(),y=new TextDecoder;if(!g)throw new Error("无法获取响应流");let v="";for(;;){const{done:_,value:I}=await g.read();if(_)break;v+=y.decode(I,{stream:!0});const m=v.split(`
`);v=m.pop()||"";for(const w of m)if(w.startsWith("data: "))try{const o=JSON.parse(w.slice(6));if(o.event==="message")c=o.answer||((u=o.message)==null?void 0:u.content)||"";else if(o.event==="message_end"||o.event==="workflow_finished")o.conversation_id&&(this.conversationId=o.conversation_id);else if(o.event==="agent_message"||o.event==="agent_thought")o.answer&&(c=o.answer);else if(o.event==="node_finished"&&o.data&&o.data.outputs){const h=o.data.outputs;(h.text||h.answer)&&(c=h.text||h.answer)}}catch(o){console.warn("解析流数据失败:",o)}}}catch(f){console.error("Dify 流式 API 调用失败:",f),c=this.getMockResponse(s).answer}c&&await this.simulateStreamResponse(c,a)}async simulateStreamResponse(s,e){for(let a=0;a<s.length;a++){e(s[a]);const l=s[a],c=/[。！？，、；：]/.test(l)?30:/[\u4e00-\u9fa5]/.test(l)?50:/\s/.test(l)?20:30;await new Promise(i=>setTimeout(i,c))}}resetConversation(){this.conversationId=null}getConversationId(){return this.conversationId}}const T=new R(P),$=(n,s)=>{const e=n.__vccOpts||n;for(const[a,l]of s)e[a]=l;return e};export{$ as _,T as d,b as u};
