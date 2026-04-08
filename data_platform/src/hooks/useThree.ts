import {
  ref,
  shallowRef,
  nextTick,
  onUnmounted,
  defineComponent,
  createVNode,
  render,
  h,
} from 'vue'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { TransformControls } from 'three/examples/jsm/controls/TransformControls.js'
import {
  CSS2DRenderer,
  CSS2DObject,
} from 'three/examples/jsm/renderers/CSS2DRenderer.js'
import { GLTFLoader, type GLTF } from 'three/examples/jsm/loaders/GLTFLoader.js'
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js'
import { isFunction } from 'lodash-es'
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js'
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js'
import { OutlinePass } from 'three/addons/postprocessing/OutlinePass.js'
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js'
// import TWEEN from '@tweenjs/tween.js'
import TWEEN from 'three/examples/jsm/libs/tween.module.js'
import * as THREE from 'three'

//基础配置 用于快速的初始化参数修改
const CONFIG = {
  CAMERA_POSITION: [0.2, 2.8, 0.4],
  CONTROL_TARGET: [0, 2.65, 0],
  DECODER_PATH: `${import.meta.env.VITE_API_DOMAIN || ''}/js/draco/gltf/`,
} as const

export function useThree() {
  const container = ref<HTMLElement>() //挂载的容器
  const scene = shallowRef<THREE.Scene>() //场景
  const camera = shallowRef<THREE.PerspectiveCamera>() //相机
  const renderer = shallowRef<THREE.WebGLRenderer>() //渲染器
  const cssRenderer = shallowRef<CSS2DRenderer>() //css2d渲染器
  const ocontrol = shallowRef<OrbitControls>() //轨道控制器
  const tcontrol = shallowRef<TransformControls>() //变换控制器
  const outlinePass = shallowRef<OutlinePass>() //outlinePass
  const hexPass = shallowRef()
  const composers = new Map() //后期处理
  const mixers: THREE.AnimationMixer[] = [] //动画混合器
  const clock = new THREE.Clock() //时钟
  const renderMixins = new Map() //渲染混合器
  const dracoLoader = new DRACOLoader() //draco加载器
  dracoLoader.setDecoderPath(CONFIG.DECODER_PATH)
  dracoLoader.setDecoderConfig({ type: 'js' })

  const boostrap = () => {
    // 确保 container 已经准备好
    if (!container.value) {
      console.warn('Container 还未准备好，延迟初始化')
      return
    }
    boostrapScene()
    boostrapCamera()
    boostrapRenderer()
    boostrapControls()
    boostrapLights()
    onAnimate()
    onWindowResize()
    addOutlineEffect()
    addHexEffect()
  }
  //Scene
  const boostrapScene = () => {
    scene.value = new THREE.Scene()
  }
  //Camera
  const boostrapCamera = () => {
    if (!container.value) {
      console.warn('Container 未准备好，无法初始化相机')
      return
    }
    const { clientWidth, clientHeight } = container.value

    camera.value = new THREE.PerspectiveCamera(
      45,
      clientWidth / clientHeight,
      0.1,
      10000
    )
    camera.value.position.set(...CONFIG.CAMERA_POSITION)
  }
  //Renderer
  const boostrapRenderer = () => {
    if (!container.value) {
      console.warn('Container 未准备好，无法初始化渲染器')
      return
    }
    
    // 确保 container 已经挂载到 DOM
    if (!container.value.getBoundingClientRect) {
      console.warn('Container 尚未挂载到 DOM')
      return
    }
    
    const { clientWidth, clientHeight } = container.value
    //Renderer
    renderer.value = new THREE.WebGLRenderer({ antialias: true, alpha: true })
    renderer.value.shadowMap.enabled = false
    // renderer.value.outputEncoding = THREE.sRGBEncoding
    renderer.value.setSize(clientWidth, clientHeight)
    renderer.value.localClippingEnabled = true
    renderer.value.setClearAlpha(0.5)
    renderer.value.domElement.className = 'webgl-renderer'
    container.value!.appendChild(renderer.value.domElement)
    //CssRenderer
    cssRenderer.value = new CSS2DRenderer()
    cssRenderer.value.setSize(clientWidth, clientHeight)
    cssRenderer.value.domElement.className = 'css2d-renderer'
    cssRenderer.value.domElement.style.position = 'absolute'
    cssRenderer.value.domElement.style.top = '0px'
    cssRenderer.value.domElement.style.pointerEvents = 'none'
    container.value!.appendChild(cssRenderer.value.domElement)
  }
  //Controls
  const boostrapControls = () => {
    ocontrol.value = new OrbitControls(
      camera.value!,
      renderer.value!.domElement
    )
    ocontrol.value.minPolarAngle = 0
    ocontrol.value.enableDamping = true
    ocontrol.value.dampingFactor = 0.1
    ocontrol.value.target.set(0, 2.65, 0)
    ocontrol.value.maxPolarAngle = THREE.MathUtils.degToRad(90) // 最大夹角 90 度
    ocontrol.value.minPolarAngle = THREE.MathUtils.degToRad(0) // 最小夹角 0 度，允许更多角度
    ocontrol.value.minDistance = 0.5
    ocontrol.value.maxDistance = 2
    
    // SolidWorks 风格：禁用左键旋转，左键专门用于选择对象
    // 右键旋转，中键平移，滚轮缩放
    ocontrol.value.mouseButtons = {
      LEFT: null as unknown as THREE.MOUSE,  // 禁用左键，用于选择
      MIDDLE: THREE.MOUSE.PAN,     // 中键平移
      RIGHT: THREE.MOUSE.ROTATE    // 右键旋转
    }
    
    // 确保功能启用
    ocontrol.value.enableRotate = true
    ocontrol.value.enablePan = true
    ocontrol.value.enableZoom = true
    
    // 确保滚轮缩放正常工作
    ocontrol.value.enableDamping = true
    ocontrol.value.dampingFactor = 0.1
    ocontrol.value.zoomSpeed = 1.0
    
    ocontrol.value.update()

    // 初始化 TransformControls（用于拖动组件和工具）
    tcontrol.value = new TransformControls(
      camera.value!,
      renderer.value!.domElement
    )
    tcontrol.value.setMode('translate') // 默认使用平移模式
    tcontrol.value.setSpace('world') // 使用世界坐标系
    tcontrol.value.showX = true
    tcontrol.value.showY = true
    tcontrol.value.showZ = true
    
    // 修改 TransformControls 的颜色为青绿色调
    setTimeout(() => {
      if (tcontrol.value) {
        tcontrol.value.traverse((child: THREE.Object3D) => {
          if (child instanceof THREE.Mesh && child.material) {
            const mat = child.material as THREE.MeshBasicMaterial
            if (mat.color) {
              // X轴（红色）改为青绿色
              if (mat.color.getHex() === 0xff0000) {
                mat.color.setHex(0x14b8a6)
              }
              // Y轴（绿色）保持或改为稍浅的青绿色
              if (mat.color.getHex() === 0x00ff00) {
                mat.color.setHex(0x5eead4)
              }
              // Z轴（蓝色）改为青绿色
              if (mat.color.getHex() === 0x0000ff) {
                mat.color.setHex(0x14b8a6)
              }
            }
          }
        })
      }
    }, 100)
    // 设置 TransformControls 的大小
    if (typeof tcontrol.value.setSize === 'function') {
      tcontrol.value.setSize(2.0)
    }
    // 确保 TransformControls 可见
    tcontrol.value.visible = true

    // 将 TransformControls 添加到场景中
    if (scene.value && !scene.value.children.includes(tcontrol.value)) {
      scene.value.add(tcontrol.value)
    }
    
    // 当拖动 TransformControls 时禁用 OrbitControls
    tcontrol.value.addEventListener('dragging-changed', (event: { value: boolean }) => {
      if (ocontrol.value) {
        ocontrol.value.enabled = !event.value
        // 确保左键始终禁用（用于选择而非旋转）
        if (ocontrol.value.mouseButtons.LEFT !== null) {
          ocontrol.value.mouseButtons.LEFT = null as unknown as THREE.MOUSE
        }
      }
    })
    
    // 监听 TransformControls 的变化事件
    tcontrol.value.addEventListener('change', () => {
      // 这个事件会在拖动时触发，确保场景更新
    })
  }
  //Lights
  const boostrapLights = () => {
    const ambientLight = new THREE.AmbientLight(0x999999, 10)
    scene.value!.add(ambientLight)
    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.5)
    directionalLight.position.set(20, 20, 20)
    directionalLight.position.multiplyScalar(1)
    directionalLight.castShadow = true
    directionalLight.shadow.mapSize = new THREE.Vector2(1024, 1024)
    // scene.value.add(new THREE.DirectionalLightHelper(directionalLight, 5))
    scene.value!.add(directionalLight)
  }
  //窗口大小变化时重新设置渲染器大小
  const onWindowResize = () => {
    const handleResize = () => {
      const { clientWidth, clientHeight } = container.value!
      camera.value!.aspect = clientWidth / clientHeight
      camera.value!.updateProjectionMatrix()
      renderer.value!.setSize(clientWidth, clientHeight)
      cssRenderer.value!.setSize(clientWidth, clientHeight)
      ocontrol.value!.update()
    }
    window.addEventListener('resize', handleResize)
    onUnmounted(() => {
      window.removeEventListener('resize', handleResize)
    })
  }
  //渲染循环
  let animationFrameId: number | null = null
  const onAnimate = () => {
    const delta = new THREE.Clock().getDelta()

    // 更新 OrbitControls
    if (ocontrol.value) {
      ocontrol.value.update()
    }

    const mixerUpdateDelta = clock.getDelta()
    mixers.forEach((mixer) => mixer.update(mixerUpdateDelta))

    // 先渲染主场景（包括 TransformControls）
    // TransformControls 是场景的一部分，会通过正常渲染显示
    if (composers.size > 0) {
      // 使用后期处理渲染
      composers.forEach((composer) => composer.render(delta))
    } else {
      // 直接渲染场景（包括 TransformControls）
      renderer.value!.render(scene.value!, camera.value!)
    }

    renderMixins.forEach((mixin) => isFunction(mixin) && mixin())
    cssRenderer.value!.render(scene.value!, camera.value!)
    TWEEN.update()
    animationFrameId = requestAnimationFrame(() => onAnimate())
  }
  //加载 GLTF/GLB 模型
  const loadGltf = (url: string): Promise<GLTF> => {
    const loader = new GLTFLoader()
    loader.setDRACOLoader(dracoLoader)
    return new Promise<GLTF>((resolve) => {
      loader.load(url, (object: GLTF) => resolve(object))
    })
  }
  //加载动画混合器(用于启动模型自带的动画)
  const loadAnimationMixer = (
    mesh: THREE.Mesh | THREE.AnimationObjectGroup | THREE.Group,
    animations: Array<THREE.AnimationClip>,
    animationName: string
  ) => {
    const mixer = new THREE.AnimationMixer(mesh)
    const clip = THREE.AnimationClip.findByName(animations, animationName)
    if (!clip) return undefined
    const action = mixer.clipAction(clip)
    action.play()
    mixers.push(mixer)
    return undefined
  }
  //加载坐标轴
  const loadAxesHelper = () => {
    const axesHelper = new THREE.AxesHelper(5000)
    scene.value!.add(axesHelper)
  }
  //通过vue文件加载CSS2D
  const loadCSS2DByVue = (component: any, props: Record<string, any>) => {
    const crender = (component: any, props: Record<string, any>) => {
      const newComponent = defineComponent({
        render: () => h(component, props),
      })
      const instance = createVNode(newComponent)
      render(instance, document.createElement('div'))
      return instance.el
    }
    const element = crender(component, props) as HTMLElement
    const css2dObject = new CSS2DObject(element)
    return css2dObject
  }
  // 加载测试场景
  const loadTestScene = () => {
    const geometry = new THREE.BoxGeometry(1, 1, 1)
    const material = new THREE.MeshBasicMaterial({ color: 0x00ff00 })
    const cube = new THREE.Mesh(geometry, material)
    scene.value!.add(cube)
  }
  //过渡动画
  const transitionAnimation = (props: {
    from: Record<string, any>
    to: Record<string, any>
    duration: number
    easing?: any
    onUpdate?: (params: Record<string, any>) => void
    onComplete?: (params: Record<string, any>) => void
  }) => {
    const {
      from,
      to,
      duration,
      easing = TWEEN.Easing.Quadratic.Out,
      onUpdate,
      onComplete,
    } = props
    return new TWEEN.Tween(from)
      .to(to, duration)
      .easing(easing)
      .onUpdate((object: any) => isFunction(onUpdate) && onUpdate(object))
      .onComplete((object: any) => isFunction(onComplete) && onComplete(object))
  }
  //平面削切动画
  const planeClippingAnimation = (config: {
    objects: Array<THREE.Object3D> // 被削切的对象
    from: number // 初始高度
    to: number // 目标高度
    during?: number // 动画时长
    easing?: any // 动画缓动函数
    onComplete?: () => void // 动画完成回调即达到target高度
  }) => {
    const { objects, during, easing, from, to, onComplete } = config

    const clippingPlane = new THREE.Plane(new THREE.Vector3(0, -1, 0), from)
    objects.forEach((object) => {
      object?.traverse((mesh: any) => {
        if (!(mesh instanceof THREE.Mesh)) return void 0
        mesh.material.clippingPlanes = [clippingPlane]
      })
    })
    return transitionAnimation({
      from: { constant: from },
      to: { constant: to },
      duration: during ?? 1000,
      easing: easing ?? TWEEN.Easing.Quadratic.Out,
      onUpdate: (object: any) => {
        clippingPlane.constant = object.constant
      },
      onComplete: () => {
        isFunction(onComplete) && onComplete()
      },
    })
  }
  //添加outline效果
  const addOutlineEffect = (config?: {
    edgeStrength?: number
    edgeGlow?: number
    edgeThickness?: number
    pulsePeriod?: number
    usePatternTexture?: boolean
    visibleEdgeColor?: string | number
    hiddenEdgeColor?: string | number
  }) => {
    const composer = new EffectComposer(renderer.value!)
    const renderPass = new RenderPass(scene.value!, camera.value!)
    composer.addPass(renderPass)
    outlinePass.value = new OutlinePass(
      new THREE.Vector2(window.innerWidth, window.innerHeight),
      scene.value!,
      camera.value!
    )
    const deafultConfig = {
      edgeStrength: 3,
      edgeGlow: 0,
      edgeThickness: 1,
      pulsePeriod: 0,
      usePatternTexture: false,
      visibleEdgeColor: '#14b8a6',
      hiddenEdgeColor: '#14b8a6',
    }
    const op = Object.assign({}, deafultConfig, config)

    outlinePass.value.edgeStrength = op.edgeStrength
    outlinePass.value.edgeGlow = op.edgeGlow
    outlinePass.value.edgeThickness = op.edgeThickness
    outlinePass.value.visibleEdgeColor.set(op.visibleEdgeColor)
    outlinePass.value.hiddenEdgeColor.set(op.hiddenEdgeColor)
    outlinePass.value.selectedObjects = []
    composer.addPass(outlinePass.value)
    const outputPass = new OutputPass()
    composer.addPass(outputPass)
    composers.set('outline', composer)
  }
  //添加outline效果
  const addHexEffect = (color?: number | string) => {
    let selected: any[] = []
    hexPass.value = {
      get selectedObjects() {
        return selected
      },
      set selectedObjects(val) {
        //先清空之前的
        selected.forEach((mesh) => {
          if (mesh.material) mesh.material.emissive.setHex(mesh.hex)
        })
        val.forEach((mesh) => {
          mesh.material = mesh.material.clone()
          mesh.hex = mesh.material.emissive.getHex()
          mesh.material.emissive.setHex(color ?? 0x888888)
        })
        selected = [...val]
      },
    }
  }

  // 模型拾取
  const addModelPick = (
    object: THREE.Object3D,
    callback: (
      intersects:
        | THREE.Intersection<THREE.Object3D<THREE.Object3DEventMap>>[]
        | []
    ) => void
  ) => {
    const handler = (event: MouseEvent) => {
      if (!container.value) return
      const el = container.value as HTMLElement
      if (!el) return
      const rect = el.getBoundingClientRect()
      if (!rect) return
      const mouse = new THREE.Vector2(
        ((event.clientX - rect.left) / rect.width) * 2 - 1,
        -((event.clientY - rect.top) / rect.height) * 2 + 1
      )
      const raycaster = new THREE.Raycaster()
      raycaster.setFromCamera(mouse, camera.value!)
      const intersects = raycaster.intersectObject(object, true)
      isFunction(callback) && callback(intersects)
      // if (intersects.length <= 0) return void 0
    }
    document.addEventListener('click', handler)
    onUnmounted(() => document.removeEventListener('click', handler))
  }

  // 模型悬浮拾取
  const addModelHoverPick = (
    object: THREE.Object3D,
    callback: (
      intersects:
        | THREE.Intersection<THREE.Object3D<THREE.Object3DEventMap>>[]
        | []
    ) => void
  ) => {
    const handler = (event: MouseEvent) => {
      if (!container.value) return
      const el = container.value as HTMLElement
      if (!el) return
      const rect = el.getBoundingClientRect()
      if (!rect) return
      const mouse = new THREE.Vector2(
        ((event.clientX - rect.left) / rect.width) * 2 - 1,
        -((event.clientY - rect.top) / rect.height) * 2 + 1
      )
      const raycaster = new THREE.Raycaster()
      raycaster.setFromCamera(mouse, camera.value!)
      const intersects = raycaster.intersectObject(object, true)
      isFunction(callback) && callback(intersects)
      // if (intersects.length <= 0) return void 0
    }
    document.addEventListener('mousemove', handler)
    onUnmounted(() => document.removeEventListener('mousemove', handler))
  }

  nextTick(() => {
    boostrap()
  })

  // 清理所有 Three.js 资源，防止内存泄漏
  onUnmounted(() => {
    // 取消动画循环
    if (animationFrameId !== null) {
      cancelAnimationFrame(animationFrameId)
      animationFrameId = null
    }

    // 停止所有动画混合器
    mixers.forEach((mixer) => mixer.stopAllAction())
    mixers.length = 0

    // 清理后期处理
    composers.forEach((composer) => composer.dispose())
    composers.clear()

    // 清理控制器
    tcontrol.value?.dispose()
    ocontrol.value?.dispose()

    // 清理渲染器
    renderer.value?.dispose()
    renderer.value?.domElement?.remove()

    // 清理 CSS2D 渲染器
    cssRenderer.value?.domElement?.remove()

    // 清理 DRACO 加载器
    dracoLoader.dispose()

    // 清理场景中所有对象
    scene.value?.traverse((object) => {
      if (object instanceof THREE.Mesh) {
        object.geometry?.dispose()
        if (Array.isArray(object.material)) {
          object.material.forEach((mat) => mat.dispose())
        } else {
          object.material?.dispose()
        }
      }
    })
    scene.value?.clear()

    renderMixins.clear()
  })

  return {
    container,
    scene,
    camera,
    renderer,
    cssRenderer,
    ocontrol,
    tcontrol,
    mixers,
    renderMixins,
    composers,
    getTransformControls: () => tcontrol.value,
    outlinePass,
    hexPass,
    loadGltf,
    loadAnimationMixer,
    loadAxesHelper,
    loadCSS2DByVue,
    loadTestScene,
    transitionAnimation,
    planeClippingAnimation,
    addModelPick,
    addModelHoverPick,
    addOutlineEffect,
    addHexEffect,
  }
}

export default useThree
