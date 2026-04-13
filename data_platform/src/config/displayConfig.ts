/**
 * 显示信息统一配置文件
 * 修改此文件可以统一更新整个系统的显示内容、字号和样式
 */

// ==================== 系统基础信息 ====================
export const SYSTEM_INFO = {
  // 公司名称
  companyName: {
    cn: '智能值守系统',
    en: 'CAUSYRA AI Fault Location System',
  },

  // 页面标题
  pageTitle: '智能值守系统',

  // 公司Logo路径
  logoPath: '/images/icon-logo.jpg',
  faviconPath: '/images/favicon.png',
}

// ==================== 字体大小配置 ====================
export const FONT_SIZES = {
  // 标题字号
  title: {
    main: '30px',        // 主标题（中文）
    sub: '10px',         // 副标题（英文）
  },

  // 头部信息字号
  header: {
    time: '16px',        // 时间、日期、星期
    temperature: '16px', // 温度
  },

  // 按钮文字
  button: {
    normal: '14px',      // 普通按钮
    large: '16px',       // 大按钮
  },

  // 面板内容
  panel: {
    label: '14px',       // 标签文字
    value: '16px',       // 数值文字
    unit: '12px',        // 单位文字
    listItem: '14px',    // 列表项文字
  },

  // 地图页面
  map: {
    statsValue: '24px',  // 统计数值
    statsLabel: '12px',  // 统计标签
    fieldName: '16px',   // 风场名称
    fieldInfo: '12px',   // 风场信息
  },

  // 聊天界面
  chat: {
    message: '14px',     // 消息文字
    time: '11px',        // 时间戳
    input: '14px',       // 输入框
  },

  // 加载页面
  loading: {
    title: '16px',       // 加载标题
    subtitle: '12px',    // 加载副标题
  },
}

// ==================== 颜色配置 ====================
export const COLORS = {
  // 主题色
  primary: '#409EFF',
  success: '#67C23A',
  warning: '#E6A23C',
  danger: '#F56C6C',
  error: '#F56C6C',
  info: '#909399',

  // 文字颜色
  text: {
    primary: '#fff',
    secondary: '#b9cfff',
    disabled: '#909399',
  },

  // 背景色
  background: {
    main: '#303133',
    panel: 'rgba(0, 0, 0, 0.3)',
    loading: '#303133',
  },

  // 状态颜色
  status: {
    normal: '#67C23A',
    warning: '#E6A23C',
    error: '#F56C6C',
    critical: '#F56C6C',
  },
}

// ==================== 按钮文字配置 ====================
export const BUTTON_TEXT = {
  // 导航按钮
  navigation: {
    backToMap: '返回地图',
    showTools: '显示工具',
    hideTools: '隐藏工具',
    videoAnalysis: 'AI分析',
    videoDetection: '视频检测',
  },

  // 操作按钮
  action: {
    save: '保存',
    cancel: '取消',
    confirm: '确认',
    delete: '删除',
    edit: '编辑',
    close: '关闭',
    submit: '提交',
    reset: '重置',
  },

  // 聊天相关
  chat: {
    send: '发送',
    login: '登录',
    register: '注册',
    logout: '退出登录',
    switchToLogin: '已有账号？去登录',
    switchToRegister: '没有账号？去注册',
  },
}

// ==================== 提示文字配置 ====================
export const MESSAGES = {
  // 加载提示
  loading: {
    title: '正在加载资源',
    subtitle: '初次加载资源可能需要较长时间,请耐心等待',
  },

  // 状态提示
  status: {
    decomposedMode: '分解模式：点击选择对象，拖动红/绿/蓝箭头移动',
    normal: '正常',
    warning: '告警',
    error: '异常',
    critical: '严重',
    abnormal: '部件异常',
  },

  // 空状态提示
  empty: {
    aiChat: '向AI助手提问关于风机的问题',
    noMessages: '暂无消息',
    noData: '暂无数据',
  },

  // 输入框占位符
  placeholder: {
    aiInput: '输入您的问题...',
    chatInput: '输入消息...',
    username: '请输入用户名',
    password: '请输入密码',
    search: '搜索...',
  },

  // 认证相关
  auth: {
    loginTitle: '登录账号',
    registerTitle: '注册账号',
    loginWelcome: '欢迎回来',
    registerWelcome: '创建您的聊天账号',
    usernameLabel: '用户名',
    passwordLabel: '密码',
  },
}

// ==================== 统计卡片配置 ====================
export const STATS_CARDS = {
  totalTurbines: {
    icon: 'fa-solid fa-tower-broadcast',
    value: '25',
    label: '风机总数',
  },
  installedCapacity: {
    icon: 'fa-solid fa-bolt',
    value: '62.5MW',
    label: '装机容量',
  },
  warningDevices: {
    icon: 'fa-solid fa-triangle-exclamation',
    value: '2',
    label: '告警设备',
  },
  aiAnalysis: {
    icon: 'fa-solid fa-brain',
    value: 'AI分析',
    label: '视频检测',
  },
}

// ==================== 风场列表配置 ====================
export const WIND_FIELDS = [
  {
    id: 1,
    name: '长岭风场',
    turbineCount: 5,
    status: 'normal',
    location: { lat: 44.2758, lng: 123.9745 },
  },
  {
    id: 2,
    name: '白城风场',
    turbineCount: 5,
    status: 'warning',
    location: { lat: 45.6196, lng: 122.8389 },
  },
  {
    id: 3,
    name: '通榆风场',
    turbineCount: 5,
    status: 'normal',
    location: { lat: 44.8133, lng: 123.0878 },
  },
  {
    id: 4,
    name: '洮南风场',
    turbineCount: 5,
    status: 'normal',
    location: { lat: 45.3353, lng: 122.7972 },
  },
  {
    id: 5,
    name: '镇赉风场',
    turbineCount: 5,
    status: 'normal',
    location: { lat: 45.8472, lng: 123.1997 },
  },
]

// ==================== 故障码定义 ====================
export const FAULT_CODES = [
  { code: 'E001', desc: '发电机温度过高', level: '严重' },
  { code: 'E002', desc: '齿轮箱润滑油压力低', level: '严重' },
  { code: 'W001', desc: '叶片振动异常', level: '警告' },
  { code: 'W002', desc: '偏航系统响应延迟', level: '警告' },
  { code: 'E003', desc: '主轴承温度异常', level: '严重' },
  { code: 'W003', desc: '变桨系统电流波动', level: '警告' },
  { code: 'E004', desc: '变流器过载保护', level: '严重' },
  { code: 'W004', desc: '冷却系统效率下降', level: '警告' },
  { code: 'E005', desc: '控制柜通讯故障', level: '严重' },
  { code: 'W005', desc: '风速传感器偏差', level: '警告' },
]

// ==================== 参数监测项配置 ====================
export const MONITOR_PARAMS = [
  {
    icon: 'fa-solid fa-temperature-three-quarters',
    label: '温度',
    defaultValue: '23',
    unit: '度',
  },
  {
    icon: 'fa-solid fa-umbrella',
    label: '湿度',
    defaultValue: '70',
    unit: '%',
  },
  {
    icon: 'fa-solid fa-fan',
    label: '气压',
    defaultValue: '23',
    unit: 'kPa',
  },
  {
    icon: 'fa-solid fa-wind',
    label: '最大风速',
    defaultValue: '11',
    unit: 'm/s',
  },
  {
    icon: 'fa-solid fa-temperature-arrow-up',
    label: '环境温度',
    defaultValue: '15',
    unit: '度',
  },
  {
    icon: 'fa-solid fa-weight-scale',
    label: '负荷率',
    defaultValue: '23',
    unit: '%',
  },
  {
    icon: 'fa-solid fa-plug',
    label: '总功率',
    defaultValue: '12',
    unit: 'kVa',
  },
  {
    icon: 'fa-solid fa-plug',
    label: '有功功率',
    defaultValue: '12',
    unit: 'kVa',
  },
  {
    icon: 'fa-solid fa-plug',
    label: '无功功率',
    defaultValue: '12',
    unit: 'kVa',
  },
]

// ==================== 设备列表配置 ====================
export const EQUIPMENTS = [
  '发动机',
  '叶片',
  '轮毂',
  '主轴',
  '发电机',
  '塔架',
  '变流器',
  '变桨系统',
  '齿轮箱',
]

// ==================== 偏航方向配置 ====================
export const YAW_DIRECTIONS = ['东', '东北', '北', '西北', '西', '西南', '南', '东南']

// ==================== 部件详情配置 ====================
export const COMPONENT_DETAILS: Record<string, Array<{ label: string; value: number | string; unit: string }>> = {
  变桨系统: [
    { label: '变桨角度', value: 15, unit: '度' },
    { label: '变桨速度', value: 2, unit: '度/秒' },
    { label: '变桨系统温度', value: 45, unit: '摄氏度' },
    { label: '电机负载', value: 3.5, unit: '千瓦' },
    { label: '变桨位置传感器反馈', value: 1.2, unit: '米' },
    { label: '故障状态', value: 0, unit: '(无故障)' },
    { label: '电源电压', value: 400, unit: '伏特' },
    { label: '桨叶压力', value: 1200, unit: '帕斯卡' },
    { label: '变桨角度变化', value: 0.5, unit: '度' },
    { label: '变桨响应时间', value: 0.1, unit: '秒' },
    { label: '电流', value: 10, unit: '安培' },
    { label: '变桨系统运行时间', value: 200, unit: '小时' },
    { label: '变桨故障次数', value: 1, unit: '' },
    { label: '系统工作状态', value: '正常', unit: '' },
    { label: '变桨电机温度', value: 60, unit: '摄氏度' },
    { label: '变桨角度限制', value: 25, unit: '度' },
  ],
  转子: [
    { label: '转子直径', value: 120, unit: '米' },
    { label: '转子重量', value: 15000, unit: '千克' },
    { label: '转子材料', value: '玻璃纤维', unit: '' },
    { label: '转速', value: 12, unit: '转/分钟' },
    { label: '最大载荷', value: 5000, unit: '牛顿' },
    { label: '转子效率', value: 85, unit: '%' },
    { label: '转子振动', value: 0.5, unit: '毫米/秒' },
    { label: '转子温度', value: 40, unit: '摄氏度' },
    { label: '转子角度', value: 180, unit: '度' },
    { label: '转子扭矩', value: 3000, unit: '牛顿米' },
  ],
  发电机: [
    { label: '发电机功率', value: 2500, unit: '千瓦' },
    { label: '发电机电压', value: 690, unit: '伏特' },
    { label: '发电机电流', value: 2000, unit: '安培' },
    { label: '发电机温度', value: 75, unit: '摄氏度' },
    { label: '发电机转速', value: 1500, unit: '转/分钟' },
    { label: '发电机效率', value: 95, unit: '%' },
    { label: '发电机振动', value: 1.2, unit: '毫米/秒' },
    { label: '发电机功率因数', value: 0.95, unit: '' },
  ],
  齿轮箱: [
    { label: '齿轮箱温度', value: 65, unit: '摄氏度' },
    { label: '齿轮箱油温', value: 55, unit: '摄氏度' },
    { label: '齿轮箱油压', value: 2.5, unit: '巴' },
    { label: '齿轮箱振动', value: 0.8, unit: '毫米/秒' },
    { label: '齿轮箱转速比', value: 100, unit: '' },
    { label: '齿轮箱扭矩', value: 5000, unit: '牛顿米' },
    { label: '齿轮箱效率', value: 97, unit: '%' },
  ],
  叶片: [
    { label: '叶片长度', value: 60, unit: '米' },
    { label: '叶片重量', value: 8000, unit: '千克' },
    { label: '叶片材料', value: '碳纤维', unit: '' },
    { label: '叶片角度', value: 15, unit: '度' },
    { label: '叶片振动', value: 0.3, unit: '毫米/秒' },
    { label: '叶片温度', value: 25, unit: '摄氏度' },
    { label: '叶片应力', value: 150, unit: '兆帕' },
  ],
  塔架: [
    { label: '塔架高度', value: 100, unit: '米' },
    { label: '塔架直径', value: 4.5, unit: '米' },
    { label: '塔架重量', value: 200000, unit: '千克' },
    { label: '塔架振动', value: 0.2, unit: '毫米/秒' },
    { label: '塔架倾斜', value: 0.1, unit: '度' },
    { label: '塔架应力', value: 100, unit: '兆帕' },
  ],
  变流器: [
    { label: '变流器功率', value: 2500, unit: '千瓦' },
    { label: '变流器电压', value: 690, unit: '伏特' },
    { label: '变流器电流', value: 2000, unit: '安培' },
    { label: '变流器温度', value: 55, unit: '摄氏度' },
    { label: '变流器效率', value: 98, unit: '%' },
    { label: '变流器频率', value: 50, unit: '赫兹' },
  ],
  轮毂: [
    { label: '轮毂直径', value: 5, unit: '米' },
    { label: '轮毂重量', value: 25000, unit: '千克' },
    { label: '轮毂温度', value: 35, unit: '摄氏度' },
    { label: '轮毂振动', value: 0.4, unit: '毫米/秒' },
    { label: '轮毂转速', value: 12, unit: '转/分钟' },
  ],
  主轴: [
    { label: '主轴长度', value: 8, unit: '米' },
    { label: '主轴直径', value: 0.8, unit: '米' },
    { label: '主轴重量', value: 15000, unit: '千克' },
    { label: '主轴温度', value: 50, unit: '摄氏度' },
    { label: '主轴振动', value: 0.6, unit: '毫米/秒' },
    { label: '主轴转速', value: 12, unit: '转/分钟' },
    { label: '主轴扭矩', value: 4000, unit: '牛顿米' },
  ],
}

// ==================== 面板标题配置 ====================
export const PANEL_TITLES = {
  faultHistory: '故障码历史',
  yawMonitor: '偏航角度监测',
  paramMonitor: '参数监测',
  runMonitor: '运行监测',
  aiAssistant: 'AI助手',
  tools: '工具面板',
  windFieldList: '风场列表',
  componentDetails: '详情',
}

// ==================== 列表标题配置 ====================
export const LIST_HEADERS = {
  windFieldList: '风场列表',
}

// ==================== 图标配置 ====================
export const ICONS = {
  // 导航图标
  navigation: {
    back: 'fa-solid fa-arrow-left',
    tools: 'fa-solid fa-toolbox',
    info: 'fa-solid fa-info-circle',
  },

  // 状态图标
  status: {
    normal: 'fa-solid fa-circle-check',
    warning: 'fa-solid fa-circle-exclamation',
    error: 'fa-solid fa-triangle-exclamation',
  },

  // 功能图标
  function: {
    user: 'fa-solid fa-user',
    robot: 'fa-solid fa-robot',
    send: 'fa-solid fa-paper-plane',
    location: 'fa-solid fa-location-dot',
    wind: 'fa-solid fa-wind',
    list: 'fa-solid fa-list-ul',
    chevronRight: 'fa-solid fa-chevron-right',
    comments: 'fa-solid fa-comments',
    check: 'fa-solid fa-check',
  },
}

// ==================== 动画配置 ====================
export const ANIMATIONS = {
  // 滚动速度（秒）
  textRoll: 20,
  lightGo: 3,

  // 更新间隔（毫秒）
  timeUpdate: 1000,
  listScroll: 3000,
}

// ==================== 温度配置 ====================
export const WEATHER = {
  defaultTemperature: '13°c',
}

// ==================== 导出所有配置 ====================
export default {
  SYSTEM_INFO,
  FONT_SIZES,
  COLORS,
  BUTTON_TEXT,
  MESSAGES,
  STATS_CARDS,
  WIND_FIELDS,
  FAULT_CODES,
  MONITOR_PARAMS,
  EQUIPMENTS,
  YAW_DIRECTIONS,
  COMPONENT_DETAILS,
  PANEL_TITLES,
  LIST_HEADERS,
  ICONS,
  ANIMATIONS,
  WEATHER,
}
