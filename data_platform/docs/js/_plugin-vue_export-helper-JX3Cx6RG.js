var I=Object.defineProperty;var _=(n,s,e)=>s in n?I(n,s,{enumerable:!0,configurable:!0,writable:!0,value:e}):n[s]=e;var f=(n,s,e)=>_(n,typeof s!="symbol"?s+"":s,e);import{r as S}from"./@vue-hjwuK2GK.js";function D(){const n=S([]);function s(){const o=localStorage.getItem("aiChatMessages");if(o)try{n.value=JSON.parse(o)}catch(c){console.error("Failed to load AI chat messages:",c),n.value=[]}}function e(){try{localStorage.setItem("aiChatMessages",JSON.stringify(n.value))}catch(o){console.error("Failed to save AI chat messages:",o)}}function t(o){n.value.push(o),e()}function a(o){if(n.value.length>0){const c=n.value[n.value.length-1];c.type==="bot"&&(c.text=o,e())}}function r(){n.value=[],localStorage.removeItem("aiChatMessages")}return s(),{aiMessages:n,addMessage:t,updateLastMessage:a,clearMessages:r,loadMessages:s,saveMessages:e}}const M=D();function R(){return M}const A="app-rQyvLNrK915xiveza2lsnIRQ",k="http://localhost:2080";class C{constructor(s,e=k){f(this,"apiKey");f(this,"apiUrl");f(this,"conversationId",null);this.apiKey=s,this.apiUrl=e,console.log("🔧 Dify Service 初始化:",{apiUrl:e,apiKey:s.substring(0,10)+"..."})}async sendMessage(s,e="default-user",t){var c;const a={inputs:{},query:s,response_mode:"blocking",user:e},r=t||this.conversationId;r&&(a.conversation_id=r);const o={"Content-Type":"application/json",Authorization:`Bearer ${this.apiKey}`};console.log("📤 发送 Dify 请求:",{url:`${this.apiUrl}/chat-messages`,query:s.substring(0,50)+"...",user:e,hasConversationId:!!(t||this.conversationId),apiKey:this.apiKey.substring(0,15)+"...",headers:o,body:a});try{const l=this.apiUrl.includes("/api/dify")?`${this.apiUrl}/v1/chat-messages`:`${this.apiUrl}/v1/chat-messages`,d=await fetch(l,{method:"POST",headers:o,body:JSON.stringify(a)});if(console.log("📥 Dify 响应状态:",d.status,d.statusText),!d.ok){const u=await d.text();return console.error("❌ Dify API 错误响应:",u),console.warn("⚠️ Dify 服务不可用，使用模拟响应"),this.getMockResponse(s)}const i=await d.json();return console.log("✅ Dify 响应数据:",{hasAnswer:!!i.answer,answerLength:((c=i.answer)==null?void 0:c.length)||0,conversationId:i.conversation_id}),i.conversation_id&&(this.conversationId=i.conversation_id),{answer:i.answer||"抱歉，我没有理解您的问题。",conversation_id:i.conversation_id,message_id:i.message_id}}catch(l){return console.error("❌ Dify API 调用失败:",l),console.warn("⚠️ Dify 服务不可用，使用模拟响应"),this.getMockResponse(s)}}getMockResponse(s){const e=s.toLowerCase();let t="";return e.includes("故障")||e.includes("告警")||e.includes("异常")?t=`我已经检测到系统中有告警信息。根据当前数据，白城风场有2台风机出现告警状态（白城-01和白城-04）。建议您：

1. 查看详细的故障日志
2. 检查风机的运行参数
3. 如有必要，安排现场检修

需要我提供更详细的故障分析吗？`:e.includes("风场")||e.includes("风机")?t=`当前系统监控着5个风场，共25台风机：

• 长岭风场：8台风机，运行正常
• 白城风场：6台风机，2台告警
• 通榆风场：5台风机，运行正常
• 洮南风场：4台风机，运行正常
• 镇赉风场：2台风机，运行正常

总装机容量：62.5MW

您想了解哪个风场的详细信息？`:e.includes("数据")||e.includes("报告")?t=`我可以为您提供以下数据报告：

• 实时运行数据
• 发电量统计
• 故障记录分析
• 维护保养记录

请告诉我您需要哪方面的数据？`:e.includes("你好")||e.includes("您好")||e.includes("hi")||e.includes("hello")?t=`您好！我是风起时域科技有限公司AI故障定位系统的智能助手。我可以帮您：

• 查询风场和风机运行状态
• 分析故障和告警信息
• 提供维护建议
• 生成数据报告

请问有什么可以帮您的吗？`:t=`我理解您的问题是关于"${s}"。作为AI助手，我可以帮您分析风场运行数据、诊断设备故障、提供维护建议等。

当前系统状态：
• 在线风机：25台
• 告警设备：2台
• 系统运行正常

您还想了解什么信息？`,{answer:t,conversation_id:"mock-conversation-"+Date.now(),message_id:"mock-message-"+Date.now()}}async sendMessageStream(s,e="default-user",t,a){var o;let r="";try{const c=this.apiUrl.includes("/api/dify")?`${this.apiUrl}/v1/chat-messages`:`${this.apiUrl}/v1/chat-messages`,l={inputs:{},query:s,response_mode:"streaming",user:e},d=a||this.conversationId;d&&(l.conversation_id=d);const i=await fetch(c,{method:"POST",headers:{Authorization:`Bearer ${this.apiKey}`,"Content-Type":"application/json"},body:JSON.stringify(l)});if(!i.ok)throw new Error(`Dify API error: ${i.status}`);const u=(o=i.body)==null?void 0:o.getReader(),y=new TextDecoder;if(!u)throw new Error("无法获取响应流");let g="";for(;;){const{done:m,value:w}=await u.read();if(m)break;g+=y.decode(w,{stream:!0});const v=g.split(`
`);g=v.pop()||"";for(const p of v)if(p.startsWith("data: "))try{const h=JSON.parse(p.slice(6));h.event==="message"?r=h.answer||"":h.event==="message_end"&&h.conversation_id&&(this.conversationId=h.conversation_id)}catch(h){console.warn("解析流数据失败:",h)}}}catch(c){console.error("❌ Dify 流式 API 调用失败:",c),console.warn("⚠️ Dify 流式服务不可用，使用模拟响应");const l=this.getMockResponse(s);r=l.answer,l.conversation_id&&(this.conversationId=l.conversation_id)}r&&await this.simulateStreamResponse(r,t)}async simulateStreamResponse(s,e){for(let t=0;t<s.length;t++){e(s[t]);const a=s[t],r=/[。！？，、；：]/.test(a)?30:/[\u4e00-\u9fa5]/.test(a)?50:/\s/.test(a)?20:30;await new Promise(o=>setTimeout(o,r))}}resetConversation(){this.conversationId=null}getConversationId(){return this.conversationId}}const U=new C(A),$=(n,s)=>{const e=n.__vccOpts||n;for(const[t,a]of s)e[t]=a;return e};export{$ as _,U as d,R as u};
