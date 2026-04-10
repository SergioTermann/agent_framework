import App from './App.vue'
import autofit from 'autofit.js'
import { createApp } from 'vue'
import router from '@/router'
import 'animate.css'
import '@/assets/fonts/DincorosBlack/result.css'
import '@/assets/fonts/DouyuFont/result.css'
import '@/assets/fonts/SarasaMonoSC/result.css'
import '@/assets/fontawesome/css/all.css'

const boostrap = async () => {
  const app = createApp(App)
  app.use(router)
  app.mount('#app')

  const ScreenSize = {
    big: [2560, 1440],
    normal: [1920, 1080],
    small: [1280, 720],
  }['normal']
  const readabilityScaleBoost = 1.02

  autofit.init({
    el: '#app',
    // Slightly reduce the design baseline so the rendered UI reads a touch larger.
    dw: Math.round(ScreenSize[0] / readabilityScaleBoost),
    dh: Math.round(ScreenSize[1] / readabilityScaleBoost),
    resize: true,
    // ignore: ['.main-middle', '.css2d-renderer', 'webgl-renderer'],
  })
}

boostrap()
