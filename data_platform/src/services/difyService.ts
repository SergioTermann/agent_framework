// Dify API 服务配置
const DIFY_API_KEY = import.meta.env.VITE_DIFY_API_KEY || ''

const DIFY_API_URL = import.meta.env.DEV 
  ? '/api/dify'
  : 'http://localhost:2080'

export interface DifyMessage {
  role: 'user' | 'assistant'
  content: string
}

export interface DifyResponse {
  answer: string
  conversation_id?: string
  message_id?: string
}

class DifyService {
  private apiKey: string
  private apiUrl: string
  private conversationId: string | null = null

  constructor(apiKey: string, apiUrl: string = DIFY_API_URL) {
    this.apiKey = apiKey
    this.apiUrl = apiUrl
  }

  async sendMessage(
    query: string,
    user: string = 'default-user',
    conversationId?: string
  ): Promise<DifyResponse> {
    const requestBody: Record<string, unknown> = {
      inputs: {},
      query: query,
      response_mode: 'blocking',
      user: user,
    }
    
    // 只有在有 conversation_id 时才添加
    const convId = conversationId || this.conversationId
    if (convId) {
      requestBody.conversation_id = convId
    }
    
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${this.apiKey}`,
    }

    try {
      const apiPath = `${this.apiUrl}/chat-messages`
      
      const response = await fetch(apiPath, {
        method: 'POST',
        headers: headers,
        body: JSON.stringify(requestBody),
      })

      if (!response.ok) {
        const errorText = await response.text()
        console.error('Dify API 错误:', response.status)
        return this.getMockResponse(query)
      }

      const data = await response.json()

      let answer = ''
      
      if (data.message && data.message.content) {
        answer = data.message.content
      } else if (data.message && data.message.answer) {
        answer = data.message.answer
      } else if (data.answer) {
        answer = data.answer
      } else if (data.result) {
        answer = data.result
      } else if (data.data && data.data.outputs) {
        answer = data.data.outputs.text || data.data.outputs.answer || data.data.outputs.result || ''
      } else if (data.outputs) {
        answer = data.outputs.text || data.outputs.answer || data.outputs.result || ''
      } else {
        answer = '抱歉，我没有理解您的问题。'
      }
      
      if (!answer) {
        answer = '抱歉，我没有理解您的问题。'
      }
      
      if (data.conversation_id) {
        this.conversationId = data.conversation_id
      }
      
      return {
        answer,
        conversation_id: data.conversation_id,
        message_id: data.message_id || data.message?.id,
      }
    } catch (error) {
      console.error('Dify API 调用失败:', error)
      return this.getMockResponse(query)
    }
  }

  private getMockResponse(query: string): DifyResponse {
    const lowerQuery = query.toLowerCase()
    
    let answer = ''
    
    if (lowerQuery.includes('故障') || lowerQuery.includes('告警') || lowerQuery.includes('异常')) {
      answer = '我已经检测到系统中有告警信息。根据当前数据，白城风场有2台风机出现告警状态（白城-01和白城-04）。建议您：\n\n1. 查看详细的故障日志\n2. 检查风机的运行参数\n3. 如有必要，安排现场检修\n\n需要我提供更详细的故障分析吗？'
    } else if (lowerQuery.includes('风场') || lowerQuery.includes('风机')) {
      answer = '当前系统监控着5个风场，共25台风机：\n\n• 长岭风场：8台风机，运行正常\n• 白城风场：6台风机，2台告警\n• 通榆风场：5台风机，运行正常\n• 洮南风场：4台风机，运行正常\n• 镇赉风场：2台风机，运行正常\n\n总装机容量：62.5MW\n\n您想了解哪个风场的详细信息？'
    } else if (lowerQuery.includes('数据') || lowerQuery.includes('报告')) {
      answer = '我可以为您提供以下数据报告：\n\n• 实时运行数据\n• 发电量统计\n• 故障记录分析\n• 维护保养记录\n\n请告诉我您需要哪方面的数据？'
    } else if (lowerQuery.includes('你好') || lowerQuery.includes('您好') || lowerQuery.includes('hi') || lowerQuery.includes('hello')) {
      answer = '您好！我是风起时域科技有限公司AI故障定位系统的智能助手。我可以帮您：\n\n• 查询风场和风机运行状态\n• 分析故障和告警信息\n• 提供维护建议\n• 生成数据报告\n\n请问有什么可以帮您的吗？'
    } else {
      answer = `我理解您的问题是关于"${query}"。作为AI助手，我可以帮您分析风场运行数据、诊断设备故障、提供维护建议等。\n\n当前系统状态：\n• 在线风机：25台\n• 告警设备：2台\n• 系统运行正常\n\n您还想了解什么信息？`
    }
    
    return {
      answer,
      conversation_id: 'mock-conversation-' + Date.now(),
      message_id: 'mock-message-' + Date.now()
    }
  }

  async sendMessageStream(
    query: string,
    user: string = 'default-user',
    onChunk: (chunk: string) => void,
    conversationId?: string
  ): Promise<void> {
    let fullAnswer = ''
    
    try {
      const apiPath = `${this.apiUrl}/chat-messages`
      
      const requestBody: Record<string, unknown> = {
        inputs: {},
        query: query,
        response_mode: 'streaming',
        user: user,
      }
      
      // 只有在有 conversation_id 时才添加
      const convId = conversationId || this.conversationId
      if (convId) {
        requestBody.conversation_id = convId
      }
      
      const response = await fetch(apiPath, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${this.apiKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody),
      })

      if (!response.ok) {
        throw new Error(`Dify API error: ${response.status}`)
      }

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()

      if (!reader) {
        throw new Error('无法获取响应流')
      }

      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6))
              
              if (data.event === 'message') {
                fullAnswer = data.answer || data.message?.content || ''
              } else if (data.event === 'message_end' || data.event === 'workflow_finished') {
                if (data.conversation_id) {
                  this.conversationId = data.conversation_id
                }
              } else if (data.event === 'agent_message' || data.event === 'agent_thought') {
                if (data.answer) {
                  fullAnswer = data.answer
                }
              } else if (data.event === 'node_finished' && data.data && data.data.outputs) {
                const outputs = data.data.outputs
                if (outputs.text || outputs.answer) {
                  fullAnswer = outputs.text || outputs.answer
                }
              }
            } catch (e) {
              console.warn('解析流数据失败:', e)
            }
          }
        }
      }
    } catch (error) {
      console.error('Dify 流式 API 调用失败:', error)
      const mockResponse = this.getMockResponse(query)
      fullAnswer = mockResponse.answer
    }
    
    // 统一使用模拟流式响应逐字输出
    if (fullAnswer) {
      await this.simulateStreamResponse(fullAnswer, onChunk)
    }
  }

  // 模拟流式响应（用于错误回退和增量输出）
  private async simulateStreamResponse(text: string, onChunk: (chunk: string) => void): Promise<void> {
    // 逐字输出，一个字一个字地显示
    for (let i = 0; i < text.length; i++) {
      onChunk(text[i])
      // 根据字符类型调整延迟时间
      // 中文字符稍慢，标点符号稍快
      const char = text[i]
      const delay = /[。！？，、；：]/.test(char) ? 30 : // 标点符号稍慢
                   /[\u4e00-\u9fa5]/.test(char) ? 50 : // 中文字符
                   /\s/.test(char) ? 20 : // 空格
                   30 // 其他字符
      await new Promise(resolve => setTimeout(resolve, delay))
    }
  }

  resetConversation() {
    this.conversationId = null
  }

  getConversationId(): string | null {
    return this.conversationId
  }
}

// 创建单例
export const difyService = new DifyService(DIFY_API_KEY)
