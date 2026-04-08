// 多模态视觉分析服务
// 支持多种多模态大模型API

// 配置项
const VISION_API_CONFIG = {
  // 使用哪个服务提供商: 'siliconflow' | 'openai' | 'claude' | 'dify' | 'qianfan' | 'local'
  provider: 'siliconflow', 
  
  // 硅基流动 SiliconFlow API
  siliconflow: {
    apiKey: import.meta.env.VITE_SILICONFLOW_API_KEY || '',
    apiUrl: 'https://api.siliconflow.cn/v1/chat/completions',
    model: 'Qwen/Qwen3-VL-8B-Thinking', // 默认模型
  },
  
  // OpenAI GPT-4 Vision API
  openai: {
    apiKey: import.meta.env.VITE_OPENAI_API_KEY || 'your-openai-api-key',
    apiUrl: import.meta.env.VITE_OPENAI_API_URL || 'https://api.openai.com/v1/chat/completions',
    model: 'gpt-4-vision-preview',
  },
  
  // Claude Vision API
  claude: {
    apiKey: import.meta.env.VITE_CLAUDE_API_KEY || 'your-claude-api-key',
    apiUrl: 'https://api.anthropic.com/v1/messages',
    model: 'claude-3-opus-20240229',
  },
  
  // Dify 多模态应用
  dify: {
    apiKey: import.meta.env.VITE_DIFY_VISION_API_KEY || '',
    apiUrl: import.meta.env.DEV ? '/api/dify' : 'http://localhost:2080',
  },
  
  // 百度千帆
  qianfan: {
    apiKey: import.meta.env.VITE_QIANFAN_API_KEY || 'your-qianfan-api-key',
    secretKey: import.meta.env.VITE_QIANFAN_SECRET_KEY || 'your-qianfan-secret-key',
    apiUrl: 'https://aip.baidubce.com/rpc/2.0/ai_custom/v1/wenxinworkshop/chat/completions_pro',
  },
  
  // 本地模型（如 LLaVA, MiniGPT-4 等）
  local: {
    apiUrl: 'http://localhost:8080/api/analyze',
  }
}

export interface VisionAnalysisResult {
  success: boolean
  analysis: string
  detectedObjects?: Array<{
    name: string
    confidence: number
    bbox?: { x: number, y: number, width: number, height: number }
    description?: string
  }>
  error?: string
}

class VisionService {
  private provider: string
  private cachedModels: string[] = [] // 缓存可用模型列表，避免重复查询
  private modelsCacheTime: number = 0 // 模型列表缓存时间
  private readonly MODELS_CACHE_DURATION = 5 * 60 * 1000 // 缓存5分钟

  constructor() {
    this.provider = VISION_API_CONFIG.provider
  }
  
  /**
   * 分析视频帧
   * @param imageData Base64编码的图像数据（可以是 data:image/jpeg;base64,... 格式）
   * @param prompt 分析提示词
   */
  async analyzeFrame(imageData: string, prompt?: string): Promise<VisionAnalysisResult> {
    const defaultPrompt = `请简要描述这张图像的主要内容，包括：
- 画面中的主要对象（人物、设备、物品等）
- 关键动作或状态
- 需要注意的重要信息

用简洁的语言输出主要内容即可。`

    const analysisPrompt = prompt || defaultPrompt
    
    try {
      let result: VisionAnalysisResult
      switch (this.provider) {
        case 'siliconflow':
          result = await this.analyzeWithSiliconFlow(imageData, analysisPrompt)
          break
        case 'openai':
          result = await this.analyzeWithOpenAI(imageData, analysisPrompt)
          break
        case 'claude':
          result = await this.analyzeWithClaude(imageData, analysisPrompt)
          break
        case 'dify':
          result = await this.analyzeWithDify(imageData, analysisPrompt)
          break
        case 'qianfan':
          result = await this.analyzeWithQianfan(imageData, analysisPrompt)
          break
        case 'local':
          result = await this.analyzeWithLocal(imageData, analysisPrompt)
          break
        default:
          throw new Error(`不支持的提供商: ${this.provider}`)
      }
      
      // 确保返回真实的分析结果
      if (!result || !result.analysis) {
        throw new Error('API返回空结果')
      }
      
      return result
    } catch (error) {
      console.error('视觉分析失败:', error)
      // 返回真实错误，不使用mock数据
      return {
        success: false,
        analysis: `分析失败: ${error instanceof Error ? error.message : String(error)}。请检查网络连接和API配置。`,
        error: String(error)
      }
    }
  }
  
  /**
   * 查询硅基流动实际可用的模型列表（带缓存，减少网络请求）
   */
  private async queryAvailableModels(): Promise<string[]> {
    // 检查缓存是否有效
    const now = Date.now()
    if (this.cachedModels.length > 0 && (now - this.modelsCacheTime) < this.MODELS_CACHE_DURATION) {
      return this.cachedModels
    }

    try {
      const modelsUrl = 'https://api.siliconflow.cn/v1/models'
      const response = await fetch(modelsUrl, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${VISION_API_CONFIG.siliconflow.apiKey}`
        }
      })

      if (response.ok) {
        const data = await response.json()
        if (data.data && Array.isArray(data.data)) {
          const models = data.data.map((m: { id?: string; name?: string }) => m.id || m.name).filter(Boolean)
          // 更新缓存
          this.cachedModels = models
          this.modelsCacheTime = now
          return models
        }
      }
    } catch (error) {
      // 查询失败，回退到缓存或默认列表
    }

    // 如果查询失败，尝试使用缓存的模型列表
    if (this.cachedModels.length > 0) {
      return this.cachedModels
    }

    // 如果没有缓存，返回常见的视觉模型列表
    const defaultModels = [
      'Qwen/Qwen3-VL-8B-Thinking', // 优先使用
      'Qwen/Qwen-VL-Chat',
      'Qwen/Qwen-VL-Max',
      'DeepSeek-VL-Chat',
      'DeepSeek-VL2-Chat',
      'deepseek-ai/DeepSeek-VL',
      'deepseek-ai/DeepSeek-VL2-Chat',
    ]
    // 缓存默认模型
    this.cachedModels = defaultModels
    this.modelsCacheTime = now
    return defaultModels
  }

  /**
   * 硅基流动 SiliconFlow 多模态分析
   * 直接使用硅基流动API，自动尝试可用的视觉模型
   */
  private async analyzeWithSiliconFlow(imageData: string, prompt: string): Promise<VisionAnalysisResult> {
    const config = VISION_API_CONFIG.siliconflow
    
    // 查询实际可用的模型列表
    let availableModels: string[] = []
    try {
      availableModels = await this.queryAvailableModels()
    } catch (error) {
      // 查询模型列表失败，使用默认列表
    }
    
    // 构建要尝试的模型列表
    const defaultModels = [
      'Qwen/Qwen3-VL-8B-Thinking', // 优先使用
      'Qwen/Qwen-VL-Chat',
      'Qwen/Qwen-VL-Max',
      'DeepSeek-VL-Chat',
      'DeepSeek-VL2-Chat',
    ]
    
    // 优先使用配置的模型，然后尝试查询到的模型，最后使用默认模型
    const modelsToTry: string[] = []
    
    // 1. 添加配置的模型
    if (config.model) {
      modelsToTry.push(config.model)
    }
    
    // 2. 添加查询到的视觉模型（过滤包含VL或Vision的）
    const visionModels = availableModels.filter(m => 
      m && (m.includes('VL') || m.includes('Vision') || m.includes('vision'))
    )
    visionModels.forEach(m => {
      if (!modelsToTry.includes(m)) {
        modelsToTry.push(m)
      }
    })
    
    // 3. 添加默认模型列表
    defaultModels.forEach(m => {
      if (!modelsToTry.includes(m)) {
        modelsToTry.push(m)
      }
    })
    
    // 4. 如果还是没有模型，添加所有查询到的模型
    if (modelsToTry.length === 0 && availableModels.length > 0) {
      modelsToTry.push(...availableModels.slice(0, 10))
    }

    let lastError: Error | null = null
    
    // 尝试每个模型，直到成功
    for (const model of modelsToTry) {
      try {
        // 构建请求体，确保格式符合硅基流动API要求
        const requestBody = {
          model: model,
          messages: [
            {
              role: 'user',
              content: [
                { type: 'text', text: prompt },
                {
                  type: 'image_url',
                  image_url: {
                    url: imageData,
                    detail: 'low' // 使用低详情模式，减少数据传输和处理时间，提升实时性能
                  }
                }
              ]
            }
          ],
          max_tokens: 2000,
          temperature: 0.7
        }
        
        const response = await fetch(config.apiUrl, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${config.apiKey}`
          },
          body: JSON.stringify(requestBody)
        })
        
        if (!response.ok) {
          const errorText = await response.text()
          let errorData: { code?: number } = {}
          try {
            errorData = JSON.parse(errorText)
          } catch {
            // 如果无法解析JSON，使用原始文本
          }

          // 检查是否是模型不存在的错误（错误码 20012）
          if (errorData.code === 20012 || errorText.includes('Model does not exist') || errorText.includes('模型不存在') || errorText.includes('does not exist')) {
            lastError = new Error(`Model ${model} does not exist`)
            continue // 尝试下一个模型
          }
          
          // 如果是认证错误，直接抛出，不继续尝试
          if (response.status === 401 || errorData.code === 401 || errorText.includes('Unauthorized') || errorText.includes('Invalid API key')) {
            throw new Error(`API密钥无效或已过期。请检查API密钥配置。`)
          }
          
          // 如果是余额不足，直接抛出
          if (response.status === 402 || errorData.code === 402 || errorText.includes('Insufficient balance') || errorText.includes('余额不足')) {
            throw new Error(`账户余额不足。请充值后再试。`)
          }
          
          // 其他错误直接抛出
          throw new Error(`SiliconFlow API error: ${response.status} - ${errorText}`)
        }
        
        const data = await response.json()

        // 如果使用的不是默认模型，更新配置以便下次使用
        if (model !== config.model) {
          config.model = model
        }
        
        // 硅基流动的响应格式类似OpenAI
        const analysisText = data.choices?.[0]?.message?.content || data.choices?.[0]?.text || ''
        
        if (!analysisText) {
          throw new Error('硅基流动API返回空结果')
        }
        
        return this.parseAnalysisResult(analysisText)
      } catch (error) {
        // 如果是模型不存在的错误，继续尝试下一个模型
        if (error instanceof Error && (
          error.message.includes('Model does not exist') || 
          error.message.includes('模型不存在') ||
          error.message.includes('does not exist')
        )) {
          lastError = error
          continue
        }
        
        // 其他错误直接抛出
        throw error
      }
    }
    
    // 所有模型都失败了
    const triedModels = modelsToTry.join(', ')
    throw new Error(`所有硅基流动视觉模型都不可用。已尝试的模型：${triedModels}。请检查：1. API密钥是否正确 2. 账户余额是否充足 3. 账户是否有权限使用视觉模型 4. 网络连接是否正常`)
  }
  
  /**
   * OpenAI GPT-4 Vision 分析
   */
  private async analyzeWithOpenAI(imageData: string, prompt: string): Promise<VisionAnalysisResult> {
    const config = VISION_API_CONFIG.openai
    
    const response = await fetch(config.apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${config.apiKey}`
      },
      body: JSON.stringify({
        model: config.model,
        messages: [
          {
            role: 'user',
            content: [
              { type: 'text', text: prompt },
              { type: 'image_url', image_url: { url: imageData } }
            ]
          }
        ],
        max_tokens: 1000
      })
    })
    
    if (!response.ok) {
      throw new Error(`OpenAI API error: ${response.status}`)
    }
    
    const data = await response.json()
    const analysisText = data.choices[0].message.content
    
    return this.parseAnalysisResult(analysisText)
  }
  
  /**
   * Claude Vision 分析
   */
  private async analyzeWithClaude(imageData: string, prompt: string): Promise<VisionAnalysisResult> {
    const config = VISION_API_CONFIG.claude
    
    // Claude 需要移除 data:image/jpeg;base64, 前缀
    const base64Data = imageData.replace(/^data:image\/\w+;base64,/, '')
    
    const response = await fetch(config.apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': config.apiKey,
        'anthropic-version': '2023-06-01'
      },
      body: JSON.stringify({
        model: config.model,
        max_tokens: 1000,
        messages: [
          {
            role: 'user',
            content: [
              {
                type: 'image',
                source: {
                  type: 'base64',
                  media_type: 'image/jpeg',
                  data: base64Data
                }
              },
              { type: 'text', text: prompt }
            ]
          }
        ]
      })
    })
    
    if (!response.ok) {
      throw new Error(`Claude API error: ${response.status}`)
    }
    
    const data = await response.json()
    const analysisText = data.content[0].text
    
    return this.parseAnalysisResult(analysisText)
  }
  
  /**
   * Dify 多模态应用分析
   */
  private async analyzeWithDify(imageData: string, prompt: string): Promise<VisionAnalysisResult> {
    const config = VISION_API_CONFIG.dify
    const apiPath = config.apiUrl.includes('/api/dify') 
      ? `${config.apiUrl}/v1/chat-messages`
      : `${config.apiUrl}/v1/chat-messages`
    
    // Dify 支持在 files 参数中传递图片
    const response = await fetch(apiPath, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${config.apiKey}`
      },
      body: JSON.stringify({
        inputs: {},
        query: prompt,
        response_mode: 'blocking',
        user: 'vision-user',
        files: [
          {
            type: 'image',
            transfer_method: 'local_file',
            upload_file_id: imageData // 或者上传后的文件ID
          }
        ]
      })
    })
    
    if (!response.ok) {
      throw new Error(`Dify API error: ${response.status}`)
    }
    
    const data = await response.json()
    const analysisText = data.answer
    
    return this.parseAnalysisResult(analysisText)
  }
  
  /**
   * 百度千帆 Vision 分析
   */
  private async analyzeWithQianfan(imageData: string, prompt: string): Promise<VisionAnalysisResult> {
    const config = VISION_API_CONFIG.qianfan
    
    // 移除 data URL 前缀
    const base64Data = imageData.replace(/^data:image\/\w+;base64,/, '')
    
    const response = await fetch(config.apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        messages: [
          {
            role: 'user',
            content: [
              { type: 'text', text: prompt },
              { type: 'image', image: base64Data }
            ]
          }
        ]
      })
    })
    
    if (!response.ok) {
      throw new Error(`Qianfan API error: ${response.status}`)
    }
    
    const data = await response.json()
    const analysisText = data.result
    
    return this.parseAnalysisResult(analysisText)
  }
  
  /**
   * 本地模型分析
   */
  private async analyzeWithLocal(imageData: string, prompt: string): Promise<VisionAnalysisResult> {
    const config = VISION_API_CONFIG.local
    
    const response = await fetch(config.apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        image: imageData,
        prompt: prompt
      })
    })
    
    if (!response.ok) {
      throw new Error(`Local API error: ${response.status}`)
    }
    
    const data = await response.json()
    return this.parseAnalysisResult(data.analysis || data.result)
  }
  
  /**
   * 解析分析结果（尝试从JSON或纯文本中提取结构化数据）
   */
  private parseAnalysisResult(analysisText: string): VisionAnalysisResult {
    try {
      // 尝试解析JSON
      const jsonMatch = analysisText.match(/\{[\s\S]*\}/)
      if (jsonMatch) {
        const parsed = JSON.parse(jsonMatch[0])
        return {
          success: true,
          analysis: parsed.summary || analysisText,
          detectedObjects: parsed.objects || parsed.detectedObjects || []
        }
      }
    } catch (e) {
      // JSON解析失败，使用文本分析
    }
    
    // 文本分析：尝试提取关键信息
    const objects: VisionAnalysisResult['detectedObjects'] = []
    
    // 查找各种对象关键词（人物、设备、环境等）
    const keywords = [
      // 人物相关
      { name: '人物', pattern: /人|person|people|worker|staff|operator/i },
      { name: '安全帽', pattern: /安全帽|helmet|hard\s*hat/i },
      { name: '工作服', pattern: /工作服|uniform|safety\s*vest/i },
      
      // 风电设备
      { name: '风机叶片', pattern: /叶片|blade|wind\s*blade/i },
      { name: '塔筒', pattern: /塔筒|tower/i },
      { name: '机舱', pattern: /机舱|nacelle/i },
      { name: '轮毂', pattern: /轮毂|hub/i },
      { name: '齿轮箱', pattern: /齿轮箱|gearbox/i },
      { name: '发电机', pattern: /发电机|generator/i },
      { name: '变流器', pattern: /变流器|converter/i },
      { name: '控制柜', pattern: /控制柜|control\s*cabinet/i },
      
      // 通用设备
      { name: '机械设备', pattern: /设备|equipment|machine|machinery/i },
      { name: '工具', pattern: /工具|tool/i },
      { name: '车辆', pattern: /车辆|vehicle|car|truck/i },
      
      // 环境
      { name: '建筑物', pattern: /建筑|building|structure/i },
      { name: '天空', pattern: /天空|sky/i },
      { name: '地面', pattern: /地面|ground|floor/i },
    ]
    
    for (const keyword of keywords) {
      if (keyword.pattern.test(analysisText)) {
        // 避免重复添加
        if (!objects.find(obj => obj.name === keyword.name)) {
          objects.push({
            name: keyword.name,
            confidence: 0.85,
            description: '在画面中检测到'
          })
        }
      }
    }
    
    return {
      success: true,
      analysis: analysisText,
      detectedObjects: objects.length > 0 ? objects : undefined
    }
  }
  
  /**
   * 获取模拟分析结果（用于演示或API不可用时）
   */
  private getMockAnalysis(): VisionAnalysisResult {
    const mockObjects = [
      { name: '风机叶片', confidence: 0.95, description: '叶片表面清洁，无明显损伤' },
      { name: '机舱', confidence: 0.92, description: '机舱外观正常，运行平稳' },
      { name: '塔筒', confidence: 0.88, description: '塔筒结构完整，无腐蚀迹象' },
    ]
    
    // 随机选择1-3个对象
    const numObjects = Math.floor(Math.random() * 3) + 1
    const selectedObjects = mockObjects.slice(0, numObjects)
    
    return {
      success: true,
      analysis: `【AI视觉分析】\n画面显示风力发电机组运行正常。检测到${numObjects}个主要部件，整体状态良好，无明显异常。建议继续定期监测。`,
      detectedObjects: selectedObjects
    }
  }
  
  /**
   * 切换服务提供商
   */
  setProvider(provider: string) {
    this.provider = provider
  }
  
  /**
   * 获取当前提供商
   */
  getProvider(): string {
    return this.provider
  }
}

// 导出单例
export const visionService = new VisionService()

