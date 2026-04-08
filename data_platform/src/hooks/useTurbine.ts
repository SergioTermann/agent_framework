import { nextTick, ref, reactive } from 'vue'
import { forEach, random } from 'lodash-es'
import useThree from './useThree'
import TWEEN from 'three/examples/jsm/libs/tween.module.js'
import * as THREE from 'three'
import WidgetLabel from '@/components/WidgetLabel.vue'

const CONFIG = {
  MODEL_SOURCES: {
    EQUIPMENT: `${import.meta.env.VITE_API_DOMAIN || ''}/models/equipment.glb`,
    PLANE: `${import.meta.env.VITE_API_DOMAIN || ''}/models/plane.glb`,
    SKELETON: `${import.meta.env.VITE_API_DOMAIN || ''}/models/skeleton.glb`,
  },
  MODEL_SCALES: [0.0001 * 3, 0.0001 * 3, 0.0001 * 3],
  EQUIPMENT_POSITION: {
    变桨系统: {
      LABEL: { x: 0.0291, y: 2.6277, z: 0.2308 },
      COMPOSE: { x: 2519.0795, y: 29288.6777, z: 0 },
      DECOMPOSE: { x: 2519.0795, y: 29000.6777, z: 300 },
    },
    转子: {
      LABEL: { x: 0.0632, y: 2.7692, z: 0.1746 },
      COMPOSE: { x: 20437.7851, y: 8650, z: 0 },
      DECOMPOSE: { x: 20437.7851, y: 8850, z: 300 },
    },
    主轴: {
      LABEL: { x: 0.0183, y: 2.6193, z: 0.0815 },
      COMPOSE: { x: 20437.7851, y: 8650, z: 0 },
      DECOMPOSE: { x: 20437.7851, y: 8350, z: 200 },
    },
    齿轮箱: {
      LABEL: { x: 0.0319, y: 2.6239, z: -0.0402 },
      COMPOSE: { x: 20437.7851, y: 8650, z: 0 },
      DECOMPOSE: { x: 20437.7851, y: 8350, z: 100 },
    },
    油冷装置: {
      LABEL: { x: 0.0364, y: 2.7995, z: 0.0593 },
      COMPOSE: { x: 20437.7851, y: 8650, z: 0 },
      DECOMPOSE: { x: 20437.7851, y: 8650, z: 600 },
    },
    偏航电机: {
      LABEL: { x: -0.0122, y: 2.75662, z: -0.0305 },
      COMPOSE: { x: 20437.7851, y: 8650, z: 0 },
      DECOMPOSE: { x: 20437.7851, y: 8850, z: 400 },
    },
    风冷装置: {
      LABEL: { x: -0.001, y: 2.7643, z: -0.1305 },
      COMPOSE: { x: 20437.7851, y: 8650, z: 0 },
      DECOMPOSE: { x: 20437.7851, y: 8750, z: 300 },
    },
    发电机: {
      LABEL: { x: 0.0047, y: 2.6156, z: -0.2045 },
      COMPOSE: { x: 20437.7851, y: 8650, z: 0 },
      DECOMPOSE: { x: 20437.7851, y: 8350, z: 0 },
    },
    控制柜: {
      LABEL: { x: 0.0249, y: 2.7605, z: -0.2521 },
      COMPOSE: { x: 20437.7851, y: 8650, z: 0 },
      DECOMPOSE: { x: 20437.7851, y: 8850, z: 0 },
    },
  },
} as const

export function useTurbine() {
  const {
    container,
    scene,
    camera,
    ocontrol,
    outlinePass,
    hexPass,
    loadGltf,
    loadAnimationMixer,
    loadCSS2DByVue,
    addModelPick,
    addModelHoverPick,
    addOutlineEffect,
    transitionAnimation,
    planeClippingAnimation,
    getTransformControls,
  } = useThree()

  const current = ref('')

  const isAnimation = ref(false)
  
  const isDecomposed = ref(false) // 是否处于分解状态
  
  const onComponentClick = ref<((componentName: string) => void) | null>(null)

  const labelGroup = new THREE.Group()
  const toolsGroup = new THREE.Group()
  const draggedToolsGroup = new THREE.Group() // 用于存放拖动的工具

  // 组件名称到标签对象的映射
  const componentLabelMap = new Map<string, THREE.CSS2DObject>()

  const models = {
    equipment: null as THREE.Group | null,
    plane: null as THREE.Group | null,
    skeleton: null as THREE.Group | null,
  }

  const skeletons = {
    color: null as THREE.Object3D | null,
    wireframe: null as THREE.Object3D | null,
  }
  
  const toolsVisible = ref(true) // 默认显示工具

  // 框选相关状态
  const isBoxSelecting = ref(false)
  const boxSelectStart = ref<{ x: number; y: number } | null>(null)
  const boxSelectEnd = ref<{ x: number; y: number } | null>(null)
  const selectedObjects = ref<THREE.Object3D[]>([]) // 多选对象列表

  const loading = reactive({
    total: 2, // 全部
    loaded: 0, // 已加载
    isLoading: true, // 执行状态
  })

  const boostrap = async () => {
    await loadModels() // 加载风机模型
    loadLights() // 加载灯光
    await openingAnimation() // 开场动画
    // 工具已移至UI面板，不再在3D场景中显示
    // createMaintenanceTools()

    addModelPick(models.equipment, (intersects) => {
      if (intersects.length > 0) {
        const obj = intersects[0]['object']
        current.value = obj.name
        outlinePass.value!.selectedObjects = [obj]
        // 触发组件点击回调
        if (onComponentClick.value) {
          onComponentClick.value(obj.name)
        }
      } else {
        current.value = ''
        outlinePass.value!.selectedObjects = []
      }
    })
    addModelHoverPick(models.equipment, (intersects) => {
      if (intersects.length > 0) {
        const obj = intersects[0]['object']
        hexPass.value!.selectedObjects = [obj]
      } else {
        hexPass.value!.selectedObjects = []
      }
    })
  }
  //加载机架和设备模型
  const loadModels = async () => {
    const loadEquipment = async () => {
      const gltf = await loadGltf(CONFIG.MODEL_SOURCES.EQUIPMENT)
      const model = gltf.scene
      model.scale.set(...CONFIG.MODEL_SCALES)
      models.equipment = model
      loading.loaded += 1
      model.name = 'equipment'
      scene.value!.add(model)
    }
    const loadSkeleton = async () => {
      const gltf = await loadGltf(CONFIG.MODEL_SOURCES.SKELETON)
      const model = gltf.scene
      loadAnimationMixer(model, gltf.animations, gltf.animations[0].name)
      model.scale.set(...CONFIG.MODEL_SCALES)
      models.skeleton = model
      loading.loaded += 1
      model.name = 'skeleton'
      scene.value!.add(model)
      skeletons.color = models.skeleton.getObjectByName('颜色材质')
      skeletons.wireframe = models.skeleton.getObjectByName('线框材质')
    }
    await Promise.all([loadEquipment(), loadSkeleton()])
    loading.isLoading = false
    loading.loaded = 2
  }
  //加载灯光
  const loadLights = () => {
    const LIGHT_LIST = [
      [0, 0, 0],
      [-100, 100, 100],
      [100, -100, 100],
      [100, 100, -100],
    ]
    forEach(LIGHT_LIST, ([x, y, z]) => {
      const directionalLight = new THREE.DirectionalLight(0xffffff, 5)
      directionalLight.position.set(x, y, z)
      scene.value?.add(directionalLight)
    })
  }

  //开场动画
  const openingAnimation = () => {
    return new Promise((resolve) => {
      isAnimation.value = true
      // 风机白色外壳平面削切动画 - 加速到 1 秒
      planeClippingAnimation({
        objects: [skeletons.color!],
        from: 4,
        to: 2,
        during: 1000 * 1,
        onComplete() {
          isAnimation.value = false
          skeletons.color!.visible = false
        },
      }).start()
      // 镜头移动 - 加速到 0.5 秒
      transitionAnimation({
        from: camera.value!.position,
        to: { x: 0.5, y: 2.8, z: 0.5 },
        duration: 1000 * 0.5,
        easing: TWEEN.Easing.Quintic.InOut,
        onUpdate: ({ x, y, z }: Record<string, number>) => {
          camera.value!.position.set(x, y, z)
          ocontrol.value?.update()
        },
        onComplete() {
          isAnimation.value = false
          resolve(void 0)
        },
      }).start()
    })
  }

  //设备分解动画: 外壳削切 => 设备分离 => 显示标签/摄像头转动
  const eqDecomposeAnimation = () => {
    return new Promise((resolve) => {
      //先确保白色外壳隐藏
      skeletons.color.visible = false
      isAnimation.value = true

      // 外壳削切动画 - 加速到 0.125 秒
      const skeletonAnimate = planeClippingAnimation({
        objects: [skeletons.wireframe],
        from: 4,
        to: 2,
        during: 1000 * 0.125,
        onComplete: () => {
          skeletons.wireframe.visible = false
          cameraAnimate.start()
        },
      })

      //可以每个部件创建一个动画，这里为了更好控制进程避免使用settimeout，只使用一个动画(更麻烦)
      const from: Record<string, number> = {}
      const to: Record<string, number> = {}

      forEach(models.equipment.children, (mesh, index) => {
        const name = mesh.name as keyof typeof CONFIG.EQUIPMENT_POSITION
        const decompose = CONFIG.EQUIPMENT_POSITION[name]['DECOMPOSE']
        const compose = CONFIG.EQUIPMENT_POSITION[name]['COMPOSE']
        from[`x${index}`] = compose.x
        from[`y${index}`] = compose.y
        from[`z${index}`] = compose.z
        to[`x${index}`] = decompose.x
        to[`y${index}`] = decompose.y
        to[`z${index}`] = decompose.z
      })

      // 设备分离动画 - 加速到 0.125 秒
      const eqAnimate = transitionAnimation({
        from,
        to,
        duration: 1000 * 0.125,
        easing: TWEEN.Easing.Quintic.InOut,
        onUpdate(data) {
          forEach(models.equipment.children, (mesh, index) => {
            mesh.position.set(
              data[`x${index}`],
              data[`y${index}`],
              data[`z${index}`]
            )
          })
        },
        onComplete: () => {
          isAnimation.value = false
          isDecomposed.value = true // 标记为已分解状态
          createEquipmentLabel()
          enableComponentDrag() // 启用组件拖动
          resolve(void 0)
        },
      })

      // 镜头转动动画 - 加速到 0.125 秒
      const cameraAnimate = transitionAnimation({
        from: camera.value!.position,
        to: { x: 0.7, y: 2.8, z: 0 },
        duration: 1000 * 0.125,
        easing: TWEEN.Easing.Linear.None,
        onUpdate(data) {
          camera.value!.position.set(data.x, data.y, data.z)
          ocontrol.value?.update()
        },
      })
      skeletonAnimate.chain(eqAnimate).start()
    })
  }

  //设备组合动画: 隐藏标签 => 设备组合 => 外壳还原
  const eqComposeAnimation = () => {
    return new Promise((resolve) => {
      isAnimation.value = true
      isDecomposed.value = false // 标记为组合状态
      disableComponentDrag() // 禁用组件拖动
      removeEquipmentLabel()

      // 镜头转动动画 - 加速到 0.125 秒
      const cameraAnimate = transitionAnimation({
        from: camera.value!.position,
        to: { x: 0.5, y: 2.8, z: 0.5 },
        duration: 1000 * 0.125,
        easing: TWEEN.Easing.Linear.None,
        onUpdate(data) {
          camera.value!.position.set(data.x, data.y, data.z)
          ocontrol.value?.update()
        },
      })
      cameraAnimate.start()
      const from: Record<string, number> = {}
      const to: Record<string, number> = {}

      forEach(models.equipment.children, (mesh, index) => {
        const name = mesh.name as keyof typeof CONFIG.EQUIPMENT_POSITION
        const decompose = CONFIG.EQUIPMENT_POSITION[name]['DECOMPOSE']
        const compose = CONFIG.EQUIPMENT_POSITION[name]['COMPOSE']
        from[`x${index}`] = decompose.x
        from[`y${index}`] = decompose.y
        from[`z${index}`] = decompose.z
        to[`x${index}`] = compose.x
        to[`y${index}`] = compose.y
        to[`z${index}`] = compose.z
      })

      // 设备组合动画 - 加速到 0.125 秒
      const eqAnimate = transitionAnimation({
        from,
        to,
        duration: 1000 * 0.125,
        easing: TWEEN.Easing.Quintic.InOut,
        onUpdate(data) {
          forEach(models.equipment.children, (mesh, index) => {
            mesh.position.set(
              data[`x${index}`],
              data[`y${index}`],
              data[`z${index}`]
            )
          })
        },
      })
      skeletons.wireframe.visible = true
      // 外壳还原动画 - 加速到 0.125 秒
      const skeletonAnimate = planeClippingAnimation({
        objects: [skeletons.wireframe],
        from: 2,
        to: 4,
        during: 1000 * 0.125,
        onComplete: () => {
          isAnimation.value = false
          resolve(void 0)
        },
      })
      eqAnimate.chain(skeletonAnimate).start()
    })
  }

  //生成设备标签
  const createEquipmentLabel = () => {
    let index = 1 // 从 1 开始编号
    componentLabelMap.clear() // 清空之前的映射
    forEach(CONFIG.EQUIPMENT_POSITION, (point, name) => {
      const label = loadCSS2DByVue(WidgetLabel, { name, number: index })
      label.position.set(point.LABEL.x, point.LABEL.y, point.LABEL.z)
      labelGroup.add(label)
      // 建立组件名称到标签的映射
      componentLabelMap.set(name, label)
      // 存储原始标签位置
      label.userData.originalPosition = { x: point.LABEL.x, y: point.LABEL.y, z: point.LABEL.z }
      label.userData.componentName = name
      index++ // 递增编号
    })
    scene.value!.add(labelGroup)
  }

  //移除设备标签
  const removeEquipmentLabel = () => {
    if (!labelGroup.children) return
    while (labelGroup.children.length > 0) {
      const child = labelGroup.children[0]
      labelGroup.remove(child)
      if (child instanceof THREE.Mesh) {
        child.geometry?.dispose()
        if (child.material instanceof THREE.Material) child.material.dispose()
      }
    }
    scene.value!.remove(labelGroup)
  }

  // 使用 TransformControls 进行组件拖动（SolidWorks 风格）
  let componentDragEnabled = false
  let selectedComponent: THREE.Object3D | null = null
  const raycaster = new THREE.Raycaster()
  const mouse = new THREE.Vector2()

  // 存储事件处理器引用以便移除
  const dragHandlers = {
    onPointerDown: null as ((e: MouseEvent) => void) | null,
    onPointerMove: null as ((e: MouseEvent) => void) | null,
    onPointerUp: null as ((e: MouseEvent) => void) | null,
    onKeyDown: null as ((e: KeyboardEvent) => void) | null,
  }
  
  // 用于区分点击和拖动
  let mouseDownTime = 0
  let mouseDownPosition = { x: 0, y: 0 }
  let isDragging = false
  let isDirectDragging = false // SolidWorks 风格：直接拖动对象
  let dragPlane: THREE.Plane | null = null // 拖动平面
  let dragOffset = new THREE.Vector3() // 拖动偏移
  const DRAG_THRESHOLD = 5 // 像素阈值，超过这个距离才算拖动

  const enableComponentDrag = () => {
    if (componentDragEnabled) {
      return
    }
    componentDragEnabled = true

    const tcontrol = getTransformControls()
    if (!tcontrol) {
      console.error('❌ TransformControls 未初始化')
      return
    }

    // 监听 TransformControls 的拖动事件
    tcontrol.addEventListener('dragging-changed', (event: { value: boolean }) => {
      if (event.value) {
        // TransformControls 开始拖动，取消框选
        isBoxSelecting.value = false
        boxSelectStart.value = null
        boxSelectEnd.value = null
      }
    })
    
    // 监听 TransformControls 的位置变化事件，同步更新标签位置
    // 注意：标签使用模型的局部坐标系统，需要转换坐标
    tcontrol.addEventListener('change', () => {
      const draggedObject = tcontrol.object
      if (draggedObject && draggedObject.name) {
        // 查找对应的标签
        const label = componentLabelMap.get(draggedObject.name)
        if (label && label.userData.originalPosition) {
          // 获取组件相对于原始位置的偏移量
          const originalPos = CONFIG.EQUIPMENT_POSITION[draggedObject.name as keyof typeof CONFIG.EQUIPMENT_POSITION]?.DECOMPOSE
          if (originalPos) {
            // 计算组件的位移（世界坐标系统）
            const deltaX = draggedObject.position.x - originalPos.x
            const deltaY = draggedObject.position.y - originalPos.y
            const deltaZ = draggedObject.position.z - originalPos.z
            
            // 标签和组件使用相同的父坐标系，直接应用相同的偏移
            // 标签坐标尺度已经是模型坐标，直接应用偏移
            const scale = 0.0001 * 3 // MODEL_SCALES
            label.position.set(
              label.userData.originalPosition.x + deltaX * scale,
              label.userData.originalPosition.y + deltaY * scale,
              label.userData.originalPosition.z + deltaZ * scale
            )
          }
        }
      }
    })

    // 鼠标按下事件
    const onPointerDown = (event: MouseEvent) => {
      // 只处理左键
      if (event.button !== 0) return
      
      // 检查 container 是否存在
      if (!container.value) {
        return
      }
      
      // 检查是否点击在 UI 元素上（避免选择 UI）
      const target = event.target as HTMLElement | null
      if (target) {
        // 如果点击的是任何 UI 面板或按钮，都不处理
        // 这包括工具面板，让它的拖放事件正常工作
        const isUIElement = target.closest('.layout-panel') || target.closest('button')
        if (isUIElement) {
          return
        }
      }
      
      const tcontrol = getTransformControls()
      
      // 先检测是否点击在对象上，只有点击在对象上才框选
      // 如果点击在空白处，让 OrbitControls 处理相机移动
      if (!camera.value) {
        return
      }
      
      const rect = container.value.getBoundingClientRect()
      const mouse = new THREE.Vector2(
        ((event.clientX - rect.left) / rect.width) * 2 - 1,
        -((event.clientY - rect.top) / rect.height) * 2 + 1
      )
      
      // 检测是否点击在对象上
      const objectsToTest: THREE.Object3D[] = []
      if (isDecomposed.value && models.equipment && models.equipment.children) {
        objectsToTest.push(...models.equipment.children)
      }
      if (toolsGroup && toolsGroup.children && toolsGroup.children.length > 0) {
        objectsToTest.push(...toolsGroup.children)
      }
      
      const raycaster = new THREE.Raycaster()
      raycaster.setFromCamera(mouse, camera.value)
      let clickedOnObject = false
      
      if (objectsToTest.length > 0) {
        try {
          const intersects = raycaster.intersectObjects(objectsToTest, true)
          clickedOnObject = intersects.length > 0
        } catch (error) {
          console.warn('⚠️ 射线检测出错:', error)
        }
      }
      
      // 检查是否点击在 TransformControls 上
      if (tcontrol && tcontrol.object) {
        try {
          const intersects = raycaster.intersectObject(tcontrol, true)
          if (intersects.length > 0) {
            // 点击在 TransformControls 上，不开始框选
            return
          }
        } catch (error) {
          // 忽略错误
        }
      }
      
      // 只有在点击到对象时才开始框选，否则让相机移动
      if (clickedOnObject) {
        // 检测点击的是哪个对象（用于直接拖动）
        try {
          const intersects = raycaster.intersectObjects(objectsToTest, true)
          if (intersects.length > 0) {
            let obj = intersects[0].object
            let depth = 0
            const maxDepth = 20
            
            // 向上查找，直到找到在 objectsToTest 数组中的对象
            while (obj.parent && depth < maxDepth) {
              if (objectsToTest.includes(obj)) {
                break
              }
              obj = obj.parent
              depth++
            }
            
            // 验证找到的对象
            if (objectsToTest.includes(obj)) {
              // 更新选中的对象（用于直接拖动）
              selectedComponent = obj
            }
          }
        } catch (error) {
          console.warn('⚠️ 检测拖动对象时出错:', error)
        }
        
        // 开始框选
        boxSelectStart.value = {
          x: event.clientX - rect.left,
          y: event.clientY - rect.top
        }
        boxSelectEnd.value = null
        isBoxSelecting.value = true
        
        // 记录按下时间和位置（用于区分点击和拖动）
        mouseDownTime = Date.now()
        mouseDownPosition = { x: event.clientX, y: event.clientY }
        isDragging = false
      } else {
        // 点击在空白处，不开始框选
        // 不要启用左键平移，避免误操作
        // 用户应该使用右键旋转、中键平移
        // 清除选中的对象
        selectedComponent = null
      }
    }

    // 鼠标移动事件
    const onPointerMove = (event: MouseEvent) => {
      const tcontrol = getTransformControls()
      
      // 如果 TransformControls 正在拖动，完全让 TransformControls 处理，不做任何干扰
      if (tcontrol && tcontrol.dragging) {
        isBoxSelecting.value = false
        boxSelectStart.value = null
        boxSelectEnd.value = null
        isDirectDragging = false
        // 不阻止事件，让 TransformControls 继续处理
        return
      }
      
      // SolidWorks 风格：直接拖动对象
      if (isDirectDragging && selectedComponent && dragPlane && camera.value && container.value) {
        const rect = container.value.getBoundingClientRect()
        const mouse = new THREE.Vector2(
          ((event.clientX - rect.left) / rect.width) * 2 - 1,
          -((event.clientY - rect.top) / rect.height) * 2 + 1
        )
        
        const raycaster = new THREE.Raycaster()
        raycaster.setFromCamera(mouse, camera.value)
        
        const intersectPoint = new THREE.Vector3()
        const hasIntersection = raycaster.ray.intersectPlane(dragPlane, intersectPoint)
        
        if (hasIntersection && intersectPoint) {
          // 计算新位置：交点 - 偏移量
          const newPosition = new THREE.Vector3().copy(intersectPoint).sub(dragOffset)
          
          // 限制移动范围，避免对象飞得太远
          const maxDistance = 10 // 最大移动距离
          if (newPosition.length() < maxDistance) {
            selectedComponent.position.copy(newPosition)
            
            // 更新标签位置（如果有）
            const label = componentLabelMap.get(selectedComponent.name)
            if (label && label.userData.offsetFromComponent) {
              selectedComponent.updateMatrixWorld(true)
              const componentWorldPos = new THREE.Vector3()
              selectedComponent.getWorldPosition(componentWorldPos)
              
              label.position.set(
                componentWorldPos.x + label.userData.offsetFromComponent.x,
                componentWorldPos.y + label.userData.offsetFromComponent.y,
                componentWorldPos.z + label.userData.offsetFromComponent.z
              )
            }
          } else {
            console.warn('⚠️ 移动距离过大，已限制')
          }
        }
        return
      }
      
      // 如果 TransformControls 附加了对象，检查是否正在与控件交互
      if (tcontrol && tcontrol.object) {
        // 让 TransformControls 优先处理事件，不干扰
        // 这里不阻止事件传播，让 TransformControls 可以正常响应
      }
      
      // 更新框选矩形
      if (isBoxSelecting.value && boxSelectStart.value && container.value) {
        const rect = container.value.getBoundingClientRect()
        boxSelectEnd.value = {
          x: event.clientX - rect.left,
          y: event.clientY - rect.top
        }
      }
      
      if (mouseDownTime === 0) return
      
      const dx = Math.abs(event.clientX - mouseDownPosition.x)
      const dy = Math.abs(event.clientY - mouseDownPosition.y)
      
      if (dx > DRAG_THRESHOLD || dy > DRAG_THRESHOLD) {
        isDragging = true
        
        // SolidWorks 风格：开始直接拖动对象（如果有选中的对象）
        if (selectedComponent && !isDirectDragging && camera.value && container.value) {
          // 创建一个与相机视角垂直的拖动平面，通过对象的当前位置
          const cameraDirection = new THREE.Vector3()
          camera.value.getWorldDirection(cameraDirection)
          cameraDirection.normalize()
          
          const objectPosition = new THREE.Vector3()
          selectedComponent.getWorldPosition(objectPosition)
          
          dragPlane = new THREE.Plane()
          dragPlane.setFromNormalAndCoplanarPoint(cameraDirection, objectPosition)
          
          // 计算鼠标射线与平面的交点，作为初始偏移
          const rect = container.value.getBoundingClientRect()
          const mouse = new THREE.Vector2(
            (mouseDownPosition.x / rect.width) * 2 - 1,
            -(mouseDownPosition.y / rect.height) * 2 + 1
          )
          
          const raycaster = new THREE.Raycaster()
          raycaster.setFromCamera(mouse, camera.value)
          
          const intersectPoint = new THREE.Vector3()
          raycaster.ray.intersectPlane(dragPlane, intersectPoint)
          
          if (intersectPoint) {
            dragOffset.copy(intersectPoint).sub(objectPosition)
            isDirectDragging = true
            isBoxSelecting.value = false // 禁用框选
          }
        }
      }
    }

    // 检测对象是否在框选区域内
    const isObjectInBox = (obj: THREE.Object3D, start: { x: number; y: number }, end: { x: number; y: number }): boolean => {
      if (!camera.value || !container.value) return false
      
      // 验证 obj 是否是有效的 Object3D
      if (!(obj instanceof THREE.Object3D)) {
        console.warn('⚠️ isObjectInBox: obj 不是有效的 Object3D', obj)
        return false
      }
      
      const rect = container.value.getBoundingClientRect()
      let box: THREE.Box3
      try {
        box = new THREE.Box3().setFromObject(obj)
      } catch (error) {
        console.warn('⚠️ 无法计算对象边界框:', error)
        return false
      }
      const center = box.getCenter(new THREE.Vector3())
      
      // 将3D中心点投影到屏幕坐标
      const vector = center.project(camera.value)
      const x = ((vector.x + 1) / 2) * rect.width
      const y = ((-vector.y + 1) / 2) * rect.height
      
      // 计算框选矩形的边界
      const minX = Math.min(start.x, end.x)
      const maxX = Math.max(start.x, end.x)
      const minY = Math.min(start.y, end.y)
      const maxY = Math.max(start.y, end.y)
      
      // 检查点是否在矩形内
      return x >= minX && x <= maxX && y >= minY && y <= maxY
    }

    // 鼠标释放事件（点击）
    const onPointerUp = (event: MouseEvent) => {
      if (event.button !== 0) return
      
      // 检查 container 是否存在
      if (!container.value) {
        mouseDownTime = 0
        isDragging = false
        isBoxSelecting.value = false
        boxSelectStart.value = null
        boxSelectEnd.value = null
        return
      }
      
      const tcontrol = getTransformControls()
      
      // 处理框选
      if (isBoxSelecting.value && boxSelectStart.value && boxSelectEnd.value) {
        const start = boxSelectStart.value
        const end = boxSelectEnd.value
        const dx = Math.abs(end.x - start.x)
        const dy = Math.abs(end.y - start.y)
        
        // 如果框选区域足够大，执行框选
        if (dx > 5 || dy > 5) {
          const objectsToTest: THREE.Object3D[] = []
          
          // 添加组件（如果在分解状态）
          if (isDecomposed.value && models.equipment && models.equipment.children) {
            objectsToTest.push(...models.equipment.children)
          }
          
          // 添加工具（任何状态）
          if (toolsGroup && toolsGroup.children && toolsGroup.children.length > 0) {
            objectsToTest.push(...toolsGroup.children)
          }
          
          // 检测框内的对象
          const boxedObjects: THREE.Object3D[] = []
          objectsToTest.forEach(obj => {
            if (isObjectInBox(obj, start, end)) {
              boxedObjects.push(obj)
            }
          })
          
          // 选中框内的对象
          if (boxedObjects.length > 0) {
            selectedObjects.value = boxedObjects
            outlinePass.value!.selectedObjects = boxedObjects
            
            // 如果只有一个对象，附加 TransformControls
            if (boxedObjects.length === 1) {
              const obj = boxedObjects[0]
              if (tcontrol && typeof tcontrol.attach === 'function') {
                tcontrol.detach()
                tcontrol.attach(obj)
                selectedComponent = obj
                tcontrol.setMode('translate')
                tcontrol.setSpace('world')
                tcontrol.showX = true
                tcontrol.showY = true
                tcontrol.showZ = true
                tcontrol.visible = true
              }
            } else {
              // 多个对象选中，不附加 TransformControls
              if (tcontrol) {
                tcontrol.detach()
              }
              selectedComponent = null
            }
          } else {
            // 没有选中任何对象，取消选择
            selectedObjects.value = []
            outlinePass.value!.selectedObjects = []
            if (tcontrol) {
              tcontrol.detach()
            }
            selectedComponent = null
          }
        } else {
          // 框选区域太小，当作点击处理
          if (!isDragging && Date.now() - mouseDownTime < 300 && mouseDownTime > 0) {
            handleObjectClick(event)
          }
        }
        
        // 清除框选状态
        isBoxSelecting.value = false
        boxSelectStart.value = null
        boxSelectEnd.value = null
      } else {
        // 没有框选，处理普通点击
        if (tcontrol && tcontrol.object) {
          if (!isDragging && Date.now() - mouseDownTime < 300 && mouseDownTime > 0) {
            handleObjectClick(event)
          }
        } else {
          if (!isDragging && Date.now() - mouseDownTime < 300 && mouseDownTime > 0) {
            handleObjectClick(event)
          }
        }
      }
      
      mouseDownTime = 0
      isDragging = false
      
      // 结束 SolidWorks 风格直接拖动
      if (isDirectDragging) {
        isDirectDragging = false
        dragPlane = null
      }
      
      // 恢复左键设置（禁用左键，用于选择）
      if (ocontrol.value) {
        ocontrol.value.mouseButtons.LEFT = null as unknown as THREE.MOUSE
      }
    }

    // 处理对象点击
    const handleObjectClick = (event: MouseEvent) => {
      
      const tcontrol = getTransformControls()
      if (!tcontrol) {
        console.error('❌ TransformControls 未找到')
        return
      }

      if (!container.value) {
        console.error('❌ Container 未找到')
        return
      }

      // 计算鼠标位置
      if (!container.value) {
        console.error('❌ Container 未找到，无法计算鼠标位置')
        return
      }
      
      const rect = container.value.getBoundingClientRect()
      if (!rect) {
        console.error('❌ 无法获取 Container 的边界矩形')
        return
      }
      
      mouse.x = ((event.clientX - rect.left) / rect.width) * 2 - 1
      mouse.y = -((event.clientY - rect.top) / rect.height) * 2 + 1


      // 射线检测 - 检测组件和工具
      const objectsToTest: THREE.Object3D[] = []
      
      // 组件只能在分解状态下选择
      if (isDecomposed.value && models.equipment && models.equipment.children) {
        objectsToTest.push(...models.equipment.children)
      }
      
      // 工具可以在任何状态下选择（因为它们是新添加的）
      if (toolsGroup && toolsGroup.children && toolsGroup.children.length > 0) {
        // 添加工具组的所有子工具
        objectsToTest.push(...toolsGroup.children)
      }
      
      // 如果没有可检测的对象，直接返回
      if (objectsToTest.length === 0) {
        return
      }

      if (!camera.value) {
        console.error('❌ Camera 未找到')
        return
      }


      raycaster.setFromCamera(mouse, camera.value!)
      // 设置射线检测阈值，允许检测更小的对象（工具可能很小）
      raycaster.params.Points = { threshold: 0.01 }
      raycaster.params.Line = { threshold: 0.01 }
      // 使用 true 参数进行递归检测，确保能检测到工具的所有子网格
      const intersects = raycaster.intersectObjects(objectsToTest, true)
      
      if (intersects.length > 0) {
      } else {
        // 如果没检测到，尝试更宽松的检测
        // 可以尝试增加阈值或使用不同的检测方法
      }

      if (intersects.length > 0) {
        // 找到实际的组件/工具对象
        let obj = intersects[0].object
        let depth = 0
        const maxDepth = 20
        
        // 向上查找，直到找到在 objectsToTest 数组中的对象
        // 这样可以确保选中的是单个组件或工具，而不是整个父容器
        while (obj.parent && depth < maxDepth) {
          // 检查当前对象是否在 objectsToTest 中
          if (objectsToTest.includes(obj)) {
            // 找到了正确的顶层对象（组件或工具）
            break
          }
          // 继续向上查找
          obj = obj.parent
          depth++
        }
        
        // 最后再次验证找到的对象是否在 objectsToTest 中
        if (!objectsToTest.includes(obj)) {
          console.warn('⚠️ 未找到有效的顶层对象，点击可能击中了非组件/工具对象')
          return
        }

        
        // 检查是否是工具
        const isTool = obj.userData?.isTool || toolsGroup.children.includes(obj)
        
        // 如果是组件且不在分解状态，不允许选择
        if (!isTool && !isDecomposed.value) {
          return
        }

        // 如果点击的是同一个对象，不取消选择（保持选中状态以便拖动）
        // 只有在点击空白处时才取消选择
        if (selectedComponent === obj) {
          // 确保 TransformControls 仍然可见且是平移模式
          tcontrol.visible = true
          tcontrol.setMode('translate') // 确保始终是平移模式
          tcontrol.showX = true
          tcontrol.showY = true
          tcontrol.showZ = true
          return
        } else {
          // TransformControls 应该在初始化时就已经添加到场景了
          // 只需要确保它可见并附加到对象
          if (tcontrol && typeof tcontrol.attach === 'function') {
            tcontrol.visible = true
            
            // 附加 TransformControls 到对象
            tcontrol.attach(obj)
            selectedComponent = obj
            outlinePass.value!.selectedObjects = [obj]
            
            // 设置 TransformControls 为平移模式（固定模式，不切换）
            tcontrol.setMode('translate')
            tcontrol.setSpace('world')
            tcontrol.showX = true
            tcontrol.showY = true
            tcontrol.showZ = true
            tcontrol.visible = true
            
            // 增大 TransformControls 的大小，确保箭头可见
            if (typeof tcontrol.setSize === 'function') {
              tcontrol.setSize(2.0)
            }
            
            // 强制更新对象矩阵
            obj.updateMatrixWorld(true)
            
            // 修改 TransformControls 的颜色为青绿色调
            setTimeout(() => {
              if (tcontrol) {
                tcontrol.traverse((child: THREE.Object3D) => {
                  if (child instanceof THREE.Mesh && child.material) {
                    const colorHex = child.material.color?.getHex()
                    // X轴（红色）改为青绿色
                    if (colorHex === 0xff0000) {
                      child.material.color.setHex(0x14b8a6)
                    }
                    // Y轴（绿色）改为浅青绿色
                    else if (colorHex === 0x00ff00) {
                      child.material.color.setHex(0x5eead4)
                    }
                    // Z轴（蓝色）改为青绿色
                    else if (colorHex === 0x0000ff) {
                      child.material.color.setHex(0x14b8a6)
                    }
                  }
                })
              }
            }, 50)
            
            // 验证 TransformControls 的设置
            
            // 确保 TransformControls 在场景中
            if (scene.value && tcontrol instanceof THREE.Object3D) {
              if (!scene.value.children.includes(tcontrol)) {
                scene.value.add(tcontrol)
              }
            } else {
              console.warn('⚠️ 无法添加 TransformControls：scene 或 tcontrol 无效', {
                scene: !!scene.value,
                tcontrol: !!tcontrol,
                isObject3D: tcontrol instanceof THREE.Object3D
              })
            }
            
            // 检查 TransformControls 的子对象（箭头）
            if (tcontrol.children && tcontrol.children.length > 0) {
              tcontrol.children.forEach((child: THREE.Object3D, index: number) => {
              })
            }
            
            // 使用 nextTick 和 setTimeout 确保 TransformControls 正确显示
            nextTick(() => {
              if (tcontrol.object === obj) {
                obj.updateMatrixWorld(true)
                // 触发 change 事件以确保渲染更新
                tcontrol.dispatchEvent({ type: 'change' } as THREE.Event<'change', THREE.Object3D>)
                
                // 再次确认设置
                tcontrol.visible = true
                tcontrol.showX = true
                tcontrol.showY = true
                tcontrol.showZ = true
                
                // 确保所有子对象都可见
                if (tcontrol && typeof tcontrol.traverse === 'function') {
                  try {
                tcontrol.traverse((child: THREE.Object3D) => {
                      if (!(child instanceof THREE.Object3D)) {
                        return
                      }
                  child.visible = true
                  if (child.material) {
                        if (Array.isArray(child.material)) {
                          child.material.forEach((mat: THREE.Material) => {
                            if (mat && mat.visible !== undefined) mat.visible = true
                          })
                        } else if (child.material.visible !== undefined) {
                    child.material.visible = true
                        }
                  }
                })
                  } catch (error) {
                    console.warn('⚠️ 遍历 TransformControls 子对象时出错:', error)
                  }
                }
                
                // 延迟一点再次更新，确保显示
                setTimeout(() => {
                  if (tcontrol.object === obj) {
                    obj.updateMatrixWorld(true)
                    tcontrol.dispatchEvent({ type: 'change' } as THREE.Event<'change', THREE.Object3D>)
                  }
                }, 50)
              }
            })
          } else {
            console.error('❌ TransformControls 未初始化或缺少 attach 方法！', tcontrol)
          }
        }
      } else {
        // 点击空白处，取消选择
        if (selectedComponent) {
          tcontrol.detach()
          selectedComponent = null
          outlinePass.value!.selectedObjects = []
        } else {
        }
      }
    }

    // 监听键盘事件（只保留 ESC 取消选择）
    const onKeyDown = (event: KeyboardEvent) => {
      // 如果输入框聚焦，不处理快捷键
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) {
        return
      }

      const tcontrol = getTransformControls()
      if (!tcontrol) {
        return
      }

      const key = event.key.toLowerCase()

      // ESC 键取消选择
      if (key === 'escape' || key === 'esc') {
        event.preventDefault()
        if (selectedComponent) {
          tcontrol.detach()
          selectedComponent = null
          outlinePass.value!.selectedObjects = []
        }
        return
      }
    }

    // 添加事件监听器（不使用 capture 模式，让 TransformControls 优先处理拖动）
    // TransformControls 需要接收鼠标事件来拖动箭头
    if (container.value) {
      // 不使用 capture 模式，让 TransformControls 先处理事件
      container.value.addEventListener('pointerdown', onPointerDown, false)
      container.value.addEventListener('pointermove', onPointerMove, false)
      container.value.addEventListener('pointerup', onPointerUp, false)
      window.addEventListener('keydown', onKeyDown)
      
    } else {
      console.error('❌ Container 不存在，无法添加事件监听器')
    }

    // 保存处理器以便后续移除
    dragHandlers.onPointerDown = onPointerDown
    dragHandlers.onPointerMove = onPointerMove
    dragHandlers.onPointerUp = onPointerUp
    dragHandlers.onKeyDown = onKeyDown

  }

  const disableComponentDrag = () => {
    if (!componentDragEnabled) return
    componentDragEnabled = false

    const tcontrol = getTransformControls()
    if (tcontrol) {
      tcontrol.detach()
    }

    if (container.value) {
      const { onPointerDown, onPointerMove, onPointerUp, onKeyDown } = dragHandlers
      // 移除事件监听器时使用相同的参数（false，非 capture 模式）
      if (onPointerDown) container.value.removeEventListener('pointerdown', onPointerDown, false)
      if (onPointerMove) container.value.removeEventListener('pointermove', onPointerMove, false)
      if (onPointerUp) container.value.removeEventListener('pointerup', onPointerUp, false)
      if (onKeyDown) window.removeEventListener('keydown', onKeyDown)
    }

    selectedComponent = null
    if (outlinePass.value) {
      outlinePass.value.selectedObjects = []
    }
  }

  // 创建维修工具
  const createMaintenanceTools = () => {
    const toolMaterial = new THREE.MeshStandardMaterial({
      color: 0xffa500,
      metalness: 0.8,
      roughness: 0.3,
    })

    const handleMaterial = new THREE.MeshStandardMaterial({
      color: 0x333333,
      metalness: 0.4,
      roughness: 0.6,
    })

    // 工具的基础位置（在风机底部前方，相机视野中心附近）
    // 开场动画后相机位置: [0.5, 2.8, 0.5]，目标: [0, 2.65, 0]
    // 将工具放在相机视野的正前方，确保可见
    // 相机看向 [0, 2.65, 0]，所以工具应该在这个位置附近
    const cameraPos = camera.value!.position
    const cameraTarget = ocontrol.value!.target
    const baseX = cameraTarget.x // 与相机目标对齐
    const baseY = cameraTarget.y - 0.1 // 稍微低于目标点
    const baseZ = cameraTarget.z + 0.5 // 在目标点前方，确保在视野内
    
    
    // 添加一个大的测试球体来验证位置
    const testSphere = new THREE.Mesh(
      new THREE.SphereGeometry(0.3, 16, 16),
      new THREE.MeshStandardMaterial({ color: 0xff0000, emissive: 0xff0000, emissiveIntensity: 0.5 })
    )
    testSphere.position.set(baseX, baseY, baseZ)
    testSphere.name = 'testSphere'
    scene.value!.add(testSphere)

    // 1. 扳手 - 大幅放大，确保可见
    const createWrench = () => {
      const wrench = new THREE.Group()
      
      // 扳手头部 - 放大3倍
      const headGeometry = new THREE.BoxGeometry(0.45, 0.12, 0.12)
      const head = new THREE.Mesh(headGeometry, toolMaterial)
      head.position.set(0, 0, 0)
      
      // 扳手柄 - 放大3倍
      const handleGeometry = new THREE.CylinderGeometry(0.045, 0.045, 0.6, 8)
      const handle = new THREE.Mesh(handleGeometry, handleMaterial)
      handle.position.set(-0.3, 0, 0)
      handle.rotation.z = Math.PI / 2
      
      wrench.add(head, handle)
      wrench.position.set(baseX - 0.2, baseY, baseZ)
      wrench.rotation.z = Math.PI / 6
      wrench.name = 'wrench'
      
      return wrench
    }

    // 2. 螺丝刀 - 放大尺寸（3倍）
    const createScrewdriver = () => {
      const screwdriver = new THREE.Group()
      
      // 螺丝刀头 - 放大3倍
      const tipGeometry = new THREE.CylinderGeometry(0.009, 0.006, 0.045, 8)
      const tip = new THREE.Mesh(tipGeometry, toolMaterial)
      tip.position.set(0, 0.075, 0)
      
      // 螺丝刀柄 - 放大3倍
      const handleGeometry = new THREE.CylinderGeometry(0.018, 0.018, 0.12, 8)
      const handle = new THREE.Mesh(handleGeometry, handleMaterial)
      handle.position.set(0, 0, 0)
      
      screwdriver.add(tip, handle)
      screwdriver.position.set(baseX - 0.1, baseY, baseZ + 0.1)
      screwdriver.rotation.z = Math.PI / 4
      screwdriver.name = 'screwdriver'
      
      return screwdriver
    }

    // 3. 钳子 - 放大尺寸（3倍）
    const createPliers = () => {
      const pliers = new THREE.Group()
      
      // 钳子头部（两个钳口） - 放大3倍
      const jawGeometry = new THREE.BoxGeometry(0.075, 0.015, 0.036)
      const jaw1 = new THREE.Mesh(jawGeometry, toolMaterial)
      jaw1.position.set(0.036, 0.009, 0)
      
      const jaw2 = new THREE.Mesh(jawGeometry, toolMaterial)
      jaw2.position.set(0.036, -0.009, 0)
      
      // 钳子柄 - 放大3倍
      const handle1Geometry = new THREE.BoxGeometry(0.12, 0.015, 0.036)
      const handle1 = new THREE.Mesh(handle1Geometry, handleMaterial)
      handle1.position.set(-0.06, 0.024, 0)
      
      const handle2 = new THREE.Mesh(handle1Geometry, handleMaterial)
      handle2.position.set(-0.06, -0.024, 0)
      
      pliers.add(jaw1, jaw2, handle1, handle2)
      pliers.position.set(baseX + 0.15, baseY, baseZ - 0.1)
      pliers.rotation.y = Math.PI / 3
      pliers.name = 'pliers'
      
      return pliers
    }

    // 4. 工具箱 - 大幅放大，确保可见（3倍）
    const createToolbox = () => {
      const toolbox = new THREE.Group()
      
      // 箱体 - 放大3倍，红色很显眼
      const boxGeometry = new THREE.BoxGeometry(0.6, 0.3, 0.45)
      const boxMaterial = new THREE.MeshStandardMaterial({
        color: 0xff0000,
        metalness: 0.5,
        roughness: 0.5,
        emissive: 0x660000, // 增强自发光，更容易看到
        emissiveIntensity: 0.5,
      })
      const box = new THREE.Mesh(boxGeometry, boxMaterial)
      
      // 把手 - 放大3倍
      const handleGeometry = new THREE.TorusGeometry(0.15, 0.018, 8, 16, Math.PI)
      const handleMesh = new THREE.Mesh(handleGeometry, handleMaterial)
      handleMesh.position.set(0, 0.15, 0)
      handleMesh.rotation.x = Math.PI / 2
      
      toolbox.add(box, handleMesh)
      toolbox.position.set(baseX, baseY - 0.1, baseZ + 0.2)
      toolbox.name = 'toolbox'
      
      return toolbox
    }

    // 5. 手电筒 - 放大尺寸（3倍）
    const createFlashlight = () => {
      const flashlight = new THREE.Group()
      
      // 手电筒筒身 - 放大3倍
      const bodyGeometry = new THREE.CylinderGeometry(0.024, 0.024, 0.15, 12)
      const bodyMaterial = new THREE.MeshStandardMaterial({
        color: 0x000000,
        metalness: 0.7,
        roughness: 0.3,
      })
      const body = new THREE.Mesh(bodyGeometry, bodyMaterial)
      body.rotation.z = Math.PI / 2
      
      // 手电筒头（发光部分） - 放大3倍，增强发光
      const headGeometry = new THREE.CylinderGeometry(0.03, 0.024, 0.045, 12)
      const headMaterial = new THREE.MeshStandardMaterial({
        color: 0xffff00,
        emissive: 0xffff00,
        emissiveIntensity: 1.5, // 增强发光强度
        metalness: 0.5,
        roughness: 0.2,
      })
      const head = new THREE.Mesh(headGeometry, headMaterial)
      head.position.set(0.096, 0, 0)
      head.rotation.z = Math.PI / 2
      
      flashlight.add(body, head)
      flashlight.position.set(baseX - 0.2, baseY, baseZ - 0.15)
      flashlight.name = 'flashlight'
      
      return flashlight
    }

    // 6. 油桶 - 放大尺寸（3倍）
    const createOilCan = () => {
      const oilcan = new THREE.Group()
      
      // 油桶身 - 放大3倍
      const bodyGeometry = new THREE.CylinderGeometry(0.048, 0.06, 0.15, 16)
      const bodyMaterial = new THREE.MeshStandardMaterial({
        color: 0x14b8a6,
        metalness: 0.6,
        roughness: 0.4,
        emissive: 0x0d9488, // 添加一点自发光
        emissiveIntensity: 0.2,
      })
      const body = new THREE.Mesh(bodyGeometry, bodyMaterial)
      
      // 油桶喷嘴 - 放大3倍
      const nozzleGeometry = new THREE.CylinderGeometry(0.009, 0.009, 0.075, 8)
      const nozzle = new THREE.Mesh(nozzleGeometry, toolMaterial)
      nozzle.position.set(0.045, 0.075, 0)
      nozzle.rotation.z = Math.PI / 4
      
      oilcan.add(body, nozzle)
      oilcan.position.set(baseX + 0.2, baseY - 0.05, baseZ + 0.1)
      oilcan.name = 'oilcan'
      
      return oilcan
    }

    // 添加所有工具到工具组
    const wrench = createWrench()
    const screwdriver = createScrewdriver()
    const pliers = createPliers()
    const toolbox = createToolbox()
    const flashlight = createFlashlight()
    const oilcan = createOilCan()
    
    toolsGroup.add(wrench)
    toolsGroup.add(screwdriver)
    toolsGroup.add(pliers)
    toolsGroup.add(toolbox)
    toolsGroup.add(flashlight)
    toolsGroup.add(oilcan)

    // 添加工具组到场景
    toolsGroup.visible = true // 默认显示工具
    toolsGroup.position.set(0, 0, 0) // 确保位置正确
    
    // 确保所有子工具都可见
    if (toolsGroup && typeof toolsGroup.traverse === 'function') {
      try {
    toolsGroup.traverse((child) => {
          if (child instanceof THREE.Object3D) {
      child.visible = true
          }
    })
      } catch (error) {
        console.warn('⚠️ 遍历工具组时出错:', error)
      }
    }
    
    scene.value!.add(toolsGroup)
    
    // 验证工具组是否成功添加到场景
    const isInScene = scene.value!.children.includes(toolsGroup)
    
    // 添加详细的调试信息
    
    // 确保工具材质正确
    if (toolsGroup && typeof toolsGroup.traverse === 'function') {
      try {
    toolsGroup.traverse((child) => {
      if (child instanceof THREE.Mesh) {
        child.castShadow = true
        child.receiveShadow = true
      }
    })
      } catch (error) {
        console.warn('⚠️ 遍历工具组材质时出错:', error)
      }
    }


    // 为工具添加悬停效果
    addModelHoverPick(toolsGroup, (intersects) => {
      if (intersects.length > 0) {
        const tool = intersects[0]['object'] as THREE.Mesh
        // 添加发光效果
        if (tool.material && 'emissive' in tool.material) {
          const material = tool.material as THREE.MeshStandardMaterial
          material.emissive = new THREE.Color(0x444444)
          material.emissiveIntensity = 0.3
        }
      }
    })
  }

  // 切换工具显示/隐藏（控制UI面板和场景中的工具实例）
  const toggleTools = () => {
    toolsVisible.value = !toolsVisible.value
    
    // 同时隐藏/显示场景中所有已添加的工具
    if (scene.value && typeof scene.value.traverse === 'function') {
      try {
      scene.value.traverse((object: THREE.Object3D) => {
          // 确保 object 是有效的 Object3D
          if (!(object instanceof THREE.Object3D)) {
            return
          }
        // 检查是否是工具对象（通过名称或userData标记）
        if (object.userData?.isTool) {
          object.visible = toolsVisible.value
        }
      })
      } catch (error) {
        console.warn('⚠️ 遍历场景对象时出错:', error)
      }
      
      // 如果隐藏工具，同时取消 TransformControls 的附加
      if (!toolsVisible.value) {
        const tcontrol = getTransformControls()
        if (tcontrol && tcontrol.object) {
          tcontrol.detach()
        }
      }
    }
  }

  // 创建3D工具并添加到场景（使用 TransformControls 拖动）
  const create3DTool = (toolName: string): THREE.Group | null => {
    // 高质量金属材质
    const chromeMaterial = new THREE.MeshStandardMaterial({
      color: 0xaaaaaa,
      metalness: 0.98,
      roughness: 0.08,
    })

    const cameraTarget = ocontrol.value!.target
    const baseX = cameraTarget.x
    const baseY = cameraTarget.y
    const baseZ = cameraTarget.z + 0.2

    switch (toolName) {
      case '扳手':
        const wrench = new THREE.Group()
        // 缩小到1/3 - 约1.7cm
        const wHead = new THREE.BoxGeometry(0.017, 0.004, 0.004)
        const head = new THREE.Mesh(wHead, chromeMaterial)
        head.position.x = 0.0067
        
        const wHandle = new THREE.CylinderGeometry(0.001, 0.001, 0.02, 6)
        const handle = new THREE.Mesh(wHandle, new THREE.MeshStandardMaterial({
          color: 0x333333,
          metalness: 0,
          roughness: 0.95,
        }))
        handle.rotation.z = Math.PI / 2
        handle.position.x = -0.0033
        
        wrench.add(head, handle)
        wrench.position.set(baseX - 0.017, baseY, baseZ - 0.01)
        wrench.name = 'wrench'
        return wrench
        
      case '螺丝刀':
        const screwdriver = new THREE.Group()
        // 缩小到1/3 - 约2cm
        const sTip = new THREE.CylinderGeometry(0.00033, 0.00027, 0.0027, 6)
        const tip = new THREE.Mesh(sTip, chromeMaterial)
        tip.position.y = 0.005
        
        const sShaft = new THREE.CylinderGeometry(0.0005, 0.0005, 0.0083, 6)
        const shaft = new THREE.Mesh(sShaft, chromeMaterial)
        shaft.position.y = 0.001
        
        const sHandle = new THREE.CylinderGeometry(0.0013, 0.0013, 0.0067, 8)
        const shandle = new THREE.Mesh(sHandle, new THREE.MeshStandardMaterial({
          color: 0xff7700,
          metalness: 0.05,
          roughness: 0.9,
        }))
        shandle.position.y = -0.0027
        
        screwdriver.add(tip, shaft, shandle)
        screwdriver.position.set(baseX - 0.0083, baseY, baseZ + 0.0083)
        screwdriver.name = 'screwdriver'
        return screwdriver
        
      case '钳子':
        const pliers = new THREE.Group()
        // 缩小到1/3 - 约1.3cm
        const pJaw1 = new THREE.BoxGeometry(0.004, 0.001, 0.002)
        const jaw1 = new THREE.Mesh(pJaw1, chromeMaterial)
        jaw1.position.set(0.002, 0.0005, 0)
        
        const jaw2 = new THREE.Mesh(pJaw1, chromeMaterial)
        jaw2.position.set(0.002, -0.0005, 0)
        
        const pHandle1 = new THREE.BoxGeometry(0.0083, 0.001, 0.002)
        const phandle1 = new THREE.Mesh(pHandle1, new THREE.MeshStandardMaterial({
          color: 0xee2222,
          metalness: 0.1,
          roughness: 0.85,
        }))
        phandle1.position.set(-0.0027, 0.0005, 0)
        
        const phandle2 = new THREE.Mesh(pHandle1, new THREE.MeshStandardMaterial({
          color: 0xee2222,
          metalness: 0.1,
          roughness: 0.85,
        }))
        phandle2.position.set(-0.0027, -0.0005, 0)
        
        pliers.add(jaw1, jaw2, phandle1, phandle2)
        pliers.position.set(baseX + 0.0083, baseY, baseZ - 0.0083)
        pliers.name = 'pliers'
        return pliers
        
      case '工具箱':
        const toolbox = new THREE.Group()
        // 缩小到1/3 - 约1.3cm
        const tBox = new THREE.BoxGeometry(0.013, 0.0083, 0.01)
        const box = new THREE.Mesh(tBox, new THREE.MeshStandardMaterial({
          color: 0xcc0000,
          metalness: 0.65,
          roughness: 0.3,
        }))
        
        const tHandle = new THREE.TorusGeometry(0.004, 0.0005, 6, 10, Math.PI)
        const thandle = new THREE.Mesh(tHandle, chromeMaterial)
        thandle.position.y = 0.005
        thandle.rotation.x = Math.PI / 2
        
        const tLatch = new THREE.BoxGeometry(0.0027, 0.00067, 0.00067)
        const latch = new THREE.Mesh(tLatch, chromeMaterial)
        latch.position.z = 0.0053
        
        toolbox.add(box, thandle, latch)
        toolbox.position.set(baseX, baseY, baseZ + 0.013)
        toolbox.name = 'toolbox'
        return toolbox
        
      case '手电筒':
        const flashlight = new THREE.Group()
        // 缩小到1/3 - 约1.7cm
        const fBody = new THREE.CylinderGeometry(0.0013, 0.0013, 0.01, 10)
        const fbody = new THREE.Mesh(fBody, new THREE.MeshStandardMaterial({
          color: 0x111111,
          metalness: 0.9,
          roughness: 0.15,
        }))
        fbody.rotation.z = Math.PI / 2
        
        const fHead = new THREE.CylinderGeometry(0.0017, 0.0013, 0.0027, 10)
        const fhead = new THREE.Mesh(fHead, new THREE.MeshStandardMaterial({
          color: 0xffffbb,
          emissive: 0xffff55,
          emissiveIntensity: 0.2,
          metalness: 0.25,
          roughness: 0.5,
          transparent: true,
          opacity: 0.95,
        }))
        fhead.position.x = 0.0063
        fhead.rotation.z = Math.PI / 2
        
        flashlight.add(fbody, fhead)
        flashlight.position.set(baseX - 0.01, baseY, baseZ - 0.017)
        flashlight.name = 'flashlight'
        return flashlight
        
      case '油桶':
        const oilcan = new THREE.Group()
        // 缩小到1/3 - 约1cm
        const oBody = new THREE.CylinderGeometry(0.0027, 0.003, 0.0067, 12)
        const obody = new THREE.Mesh(oBody, new THREE.MeshStandardMaterial({
          color: 0x14b8a6,
          metalness: 0.8,
          roughness: 0.25,
        }))
        
        const oNozzle = new THREE.CylinderGeometry(0.0004, 0.0004, 0.004, 6)
        const nozzle = new THREE.Mesh(oNozzle, chromeMaterial)
        nozzle.position.set(0.0023, 0.004, 0)
        nozzle.rotation.z = Math.PI / 4
        
        const oHandle = new THREE.TorusGeometry(0.002, 0.00027, 6, 10, Math.PI)
        const ohandle = new THREE.Mesh(oHandle, chromeMaterial)
        ohandle.position.y = 0.004
        ohandle.rotation.x = Math.PI / 2
        
        oilcan.add(obody, nozzle, ohandle)
        oilcan.position.set(baseX + 0.01, baseY, baseZ + 0.005)
        oilcan.name = 'oilcan'
        return oilcan
        
      default:
        console.warn(`未知工具: ${toolName}`)
        return null
    }
  }

  // 添加可拖动工具到场景（使用 TransformControls）
  const addDraggableTool = (toolName: string) => {
    addDraggableToolAtPosition(toolName, null)
  }

  // 在指定位置添加可拖动工具
  const addDraggableToolAtPosition = (toolName: string, mousePosition: { x: number; y: number } | null) => {
    
    const tool = create3DTool(toolName)
    if (!tool) {
      console.error('❌ 无法创建工具:', toolName)
      return
    }

    // 验证 tool 是否是有效的 Three.js Object3D
    if (!(tool instanceof THREE.Object3D)) {
      console.error('❌ 工具不是有效的 THREE.Object3D 实例:', tool)
      return
    }

    // 验证 tool 是否有 traverse 方法
    if (typeof tool.traverse !== 'function') {
      console.error('❌ 工具没有 traverse 方法:', tool)
      return
    }

    // 为工具添加唯一标识符（基于时间戳和随机数）
    const uniqueId = `${toolName}_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`
    tool.name = `${tool.name}_${uniqueId}`
    tool.userData.uniqueId = uniqueId
    tool.userData.isTool = true // 标记为工具对象，用于显示/隐藏控制

    // 如果提供了鼠标位置，计算3D位置
    if (mousePosition) {
      const raycaster = new THREE.Raycaster()
      const mouse = new THREE.Vector2(mousePosition.x, mousePosition.y)
      raycaster.setFromCamera(mouse, camera.value!)

      // 创建一个平面用于放置工具（在相机目标点高度）
      const cameraTarget = ocontrol.value!.target
      const plane = new THREE.Plane(new THREE.Vector3(0, 1, 0), -cameraTarget.y)
      const intersection = new THREE.Vector3()
      
      if (raycaster.ray.intersectPlane(plane, intersection)) {
        // 将工具放置在交点位置
        tool.position.copy(intersection)
      } else {
        // 如果无法计算交点，使用默认位置（相机前方）
        const cameraPos = camera.value!.position
        const direction = new THREE.Vector3()
          .subVectors(cameraTarget, cameraPos)
          .normalize()
        const distance = 1.0 // 距离相机1个单位
        tool.position.copy(cameraPos).add(direction.multiplyScalar(distance))
        tool.position.y = cameraTarget.y - 0.1 // 稍微低于目标点
      }
    } else {
      // 没有提供位置，使用默认位置
      const cameraTarget = ocontrol.value!.target
      tool.position.set(cameraTarget.x, cameraTarget.y - 0.1, cameraTarget.z + 0.5)
    }

    // 确保工具可见且可交互
    tool.visible = true
    // 设置工具的用户数据，标识它是工具
    tool.userData.isTool = true
    tool.userData.toolName = toolName
    
    // 安全地遍历工具对象树
    try {
      if (tool && typeof tool.traverse === 'function') {
    tool.traverse((child: THREE.Object3D) => {
          // 确保 child 是有效的 Object3D
          if (!(child instanceof THREE.Object3D)) {
            console.warn('⚠️ 发现无效的子对象:', child)
            return
          }
          
      child.visible = true
      if (child.isMesh) {
        child.castShadow = true
        child.receiveShadow = true
        // 确保所有网格都是可点击的
        child.userData.isTool = true
        child.userData.toolName = toolName
        // 确保网格可以被射线检测到
            if (typeof THREE.Mesh.prototype.raycast === 'function') {
        child.raycast = THREE.Mesh.prototype.raycast
            }
        // 增加边界框，帮助射线检测
        if (child.geometry) {
              try {
          child.geometry.computeBoundingBox()
          child.geometry.computeBoundingSphere()
              } catch (error) {
                console.warn('⚠️ 无法计算几何体边界框:', error)
              }
        }
      }
    })
      } else {
        console.error('❌ 工具对象无效或没有 traverse 方法:', tool)
        return
      }
    } catch (error) {
      console.error('❌ 遍历工具对象树时出错:', error)
      return
    }
    
    // 确保工具组本身也可以被检测
    tool.raycast = THREE.Group.prototype.raycast

    // 添加工具到场景（不清除旧工具，允许多个工具）
    if (toolsGroup && tool) {
    toolsGroup.add(tool)
      if (scene.value && !scene.value.children.includes(toolsGroup)) {
        scene.value.add(toolsGroup)
      }
    }


    // 确保拖动系统已启用（即使不在分解状态，工具也应该可以拖动）
    if (!componentDragEnabled) {
      enableComponentDrag()
    } else {
    }

    // 使用 TransformControls 附加到工具（自动选中）
    const tcontrol = getTransformControls()
    if (tcontrol && typeof tcontrol.attach === 'function') {
      // TransformControls 应该在初始化时就已经添加到场景了
      // 只需要确保它可见并附加到工具
      tcontrol.visible = true
      
      // 先取消之前的选择（如果有）
      if (tcontrol.object) {
        tcontrol.detach()
      }
      
      // 附加到工具
      tcontrol.attach(tool)
      selectedComponent = tool
      outlinePass.value!.selectedObjects = [tool]
      
      // 确保 TransformControls 在场景中
      if (scene.value && tcontrol instanceof THREE.Object3D) {
        if (!scene.value.children.includes(tcontrol)) {
          scene.value.add(tcontrol)
        }
      } else {
        console.warn('⚠️ 无法添加 TransformControls：scene 或 tcontrol 无效')
      }
      
      // 设置 TransformControls 为平移模式（固定模式）
      tcontrol.setMode('translate')
      tcontrol.setSpace('world')
      tcontrol.showX = true
      tcontrol.showY = true
      tcontrol.showZ = true
      tcontrol.visible = true
      
      // 增大 TransformControls 的大小，确保箭头可见
      if (typeof tcontrol.setSize === 'function') {
        tcontrol.setSize(2.0)
      }
      
      // 验证设置
      
      // 计算工具的边界框大小（仅用于日志记录）
      let maxSize = 0
      try {
      const box = new THREE.Box3().setFromObject(tool)
      const size = box.getSize(new THREE.Vector3())
        maxSize = Math.max(size.x, size.y, size.z)
      
      } catch (error) {
        console.warn('⚠️ 无法计算工具边界框:', error)
      }
      
      // 工具保持原始大小，不自动放大
      // TransformControls 会自动适应对象大小
      
      // 确保 TransformControls 的所有子对象（箭头）都可见
      if (tcontrol && typeof tcontrol.traverse === 'function') {
        try {
      tcontrol.traverse((child: THREE.Object3D) => {
            if (!(child instanceof THREE.Object3D)) {
              return
            }
        if (child.visible !== undefined) {
          child.visible = true
        }
        if (child.material) {
          if (Array.isArray(child.material)) {
            child.material.forEach((mat: THREE.Material) => {
              if (mat) mat.visible = true
            })
          } else if (child.material.visible !== undefined) {
            child.material.visible = true
          }
        }
      })
        } catch (error) {
          console.warn('⚠️ 遍历 TransformControls 子对象时出错:', error)
        }
      }
      
      // 检查 TransformControls 的子对象
      
      // 遍历 TransformControls 的所有子对象，确保它们都可见
      if (tcontrol && typeof tcontrol.traverse === 'function') {
        try {
      tcontrol.traverse((child: THREE.Object3D) => {
            if (!(child instanceof THREE.Object3D)) {
              return
            }
        if (child.visible !== undefined) {
          child.visible = true
        }
        if (child.material) {
          if (Array.isArray(child.material)) {
            child.material.forEach((mat: THREE.Material) => {
              if (mat && mat.visible !== undefined) mat.visible = true
            })
          } else if (child.material.visible !== undefined) {
            child.material.visible = true
          }
        }
      })
        } catch (error) {
          console.warn('⚠️ 遍历 TransformControls 子对象时出错:', error)
        }
      }
      
      // 强制触发一次渲染更新
      setTimeout(() => {
        if (tcontrol.object === tool) {
          tool.updateMatrixWorld(true)
          tcontrol.dispatchEvent({ type: 'change' } as THREE.Event<'change', THREE.Object3D>)
          
          // 再次检查子对象
          if (tcontrol && typeof tcontrol.traverse === 'function') {
            try {
          tcontrol.traverse((child: THREE.Object3D) => {
                if (!(child instanceof THREE.Object3D)) {
                  return
                }
            if (child.visible !== undefined && !child.visible) {
              console.warn('⚠️ 发现不可见的子对象:', child.type, child.name)
              child.visible = true
            }
          })
            } catch (error) {
              console.warn('⚠️ 遍历 TransformControls 子对象时出错:', error)
            }
          }
        }
      }, 200)
      
      // 强制设置 TransformControls 的显示属性
      
      // 强制更新工具矩阵
      tool.updateMatrixWorld(true)
      
      // 验证附加是否成功
      
      // 强制更新一次
      if (ocontrol.value) {
        ocontrol.value.update()
      }
      
      // 使用 nextTick 确保 TransformControls 正确更新
      nextTick(() => {
        // 强制更新工具的矩阵世界
        if (tcontrol.object === tool) {
          // 更新工具的矩阵世界（TransformControls 会自动更新自己的矩阵）
          tool.updateMatrixWorld(true)
          // 触发 change 事件以确保渲染更新
          tcontrol.dispatchEvent({ type: 'change' } as THREE.Event<'change', THREE.Object3D>)
          
          // 再次确认 TransformControls 已附加
        }
      })
      
      // 延迟一点时间再次更新工具矩阵，确保 TransformControls 正确显示
      setTimeout(() => {
        if (tcontrol.object === tool) {
          tool.updateMatrixWorld(true)
        }
      }, 100)
      
      } else {
        console.error('❌ TransformControls 未初始化或缺少 attach 方法！', tcontrol)
      }
    }
  
  // 相机拉近动画（双击工具时调用）
  const zoomInCamera = (targetPosition?: { x?: number; y?: number; z?: number }) => {
    return new Promise((resolve) => {
      if (isAnimation.value) {
        return
      }
      
      isAnimation.value = true
      const currentPos = camera.value!.position
      const currentTarget = ocontrol.value!.target
      
      // 计算拉近后的位置：相机向目标点移动，距离缩短到原来的0.6倍
      const direction = new THREE.Vector3()
        .subVectors(currentTarget, currentPos)
        .normalize()
      
      const distance = currentPos.distanceTo(currentTarget)
      const newDistance = distance * 0.6 // 拉近到60%的距离
      
      const newPosition = {
        x: currentTarget.x - direction.x * newDistance,
        y: currentTarget.y - direction.y * newDistance + (targetPosition?.y || 0),
        z: currentTarget.z - direction.z * newDistance + (targetPosition?.z || 0),
      }
      
      // 如果提供了目标位置，使用目标位置
      if (targetPosition) {
        if (targetPosition.x !== undefined) newPosition.x = targetPosition.x
        if (targetPosition.y !== undefined) newPosition.y = targetPosition.y
        if (targetPosition.z !== undefined) newPosition.z = targetPosition.z
      }
      
      
      transitionAnimation({
        from: { x: currentPos.x, y: currentPos.y, z: currentPos.z },
        to: newPosition,
        duration: 1000 * 0.8, // 0.8秒动画
        easing: TWEEN.Easing.Quintic.InOut,
        onUpdate: ({ x, y, z }: Record<string, number>) => {
          camera.value!.position.set(x, y, z)
          ocontrol.value?.update()
        },
        onComplete() {
          isAnimation.value = false
          resolve(void 0)
        },
      }).start()
    })
  }

  const warningTimer = ref()

  //开始模拟设备告警
  const startWarning = () => {
    models.equipment!.children.forEach((mesh: THREE.Object3D) => {
      if (!(mesh instanceof THREE.Mesh)) return
      mesh.material = mesh.material.clone()
      mesh.hex = mesh.material.emissive.getHex()
    })

    const handle = () => {
      if (!models.equipment || !models.equipment.children || models.equipment.children.length === 0) {
        return
      }
      const currentIndex = random(0, models.equipment.children.length - 1)
      const currentName = models.equipment.children[currentIndex].name
      models.equipment!.children.forEach((mesh: THREE.Object3D, index: number) => {
        if (!(mesh instanceof THREE.Mesh)) return
        if (index === currentIndex) {
          mesh.material.emissive.setHex(0xff0000)
        } else {
          mesh.material.emissive.setHex(mesh.hex)
        }
      })
      // 镜头移动动画 - 加速到 0.5 秒
      transitionAnimation({
        from: camera.value!.position,
        to: { x: 0.7, y: 2.8, z: 0 },
        duration: 1000 * 0.5,
        easing: TWEEN.Easing.Linear.None,
        onUpdate(data) {
          camera.value!.position.set(data.x, data.y, data.z)
          ocontrol.value?.update()
        },
      }).start()
    }
    handle()
    // 告警切换间隔 - 加速到 0.5 秒
    warningTimer.value = setInterval(handle, 1000 * 0.5)
  }

  //结束模拟设备告警
  const stopWarning = () => {
    clearInterval(warningTimer.value)
    models.equipment!.children.forEach((mesh: THREE.Object3D) => {
      if (!(mesh instanceof THREE.Mesh)) return
      mesh.material.emissive.setHex((mesh as THREE.Mesh & { hex: number }).hex)
    })

    // 镜头复位动画 - 加速到 0.5 秒
    transitionAnimation({
      from: camera.value!.position,
      to: { x: 0.5, y: 2.8, z: 0.5 },
      duration: 1000 * 0.5,
      easing: TWEEN.Easing.Linear.None,
      onUpdate(data) {
        camera.value!.position.set(data.x, data.y, data.z)
        ocontrol.value?.update()
      },
    }).start()
  }

  // 等待 container 准备好后再初始化
  const initWhenReady = async () => {
    // 等待 container 准备好
    let retries = 0
    while (!container.value && retries < 50) {
      await new Promise(resolve => setTimeout(resolve, 100))
      retries++
    }
    
    if (!container.value) {
      console.error('❌ Container 未准备好，无法初始化')
      return
    }
    
    // 确保 container 已经挂载到 DOM
    await nextTick()
    
    try {
      await boostrap()
    } catch (error) {
      console.error('❌ 初始化失败:', error)
    }
  }
  
  // 延迟初始化，确保 DOM 已经准备好
  nextTick(() => {
    initWhenReady()
  })

  return {
    container,
    loading,
    current,
    eqDecomposeAnimation,
    eqComposeAnimation,
    startWarning,
    stopWarning,
    onComponentClick,
    toggleTools,
    toolsVisible,
    zoomInCamera,
    addDraggableTool,
    addDraggableToolAtPosition,
    isDecomposed, // 导出分解状态
    // 框选相关
    isBoxSelecting,
    boxSelectStart,
    boxSelectEnd,
    selectedObjects,
  }
}

export default useTurbine

