import { createApp } from 'vue'
import App from './ui/App.vue'
import { router } from './ui/router'
import { modelServiceKey } from './ui/keys'
import { makeModelService } from './application/ModelService'
import { makeHttpModelRepository } from './adapters/http/HttpModelRepository'
import './ui/diagram-types'
import './ui/styles/shared.css'

const app = createApp(App)
app.use(router)
app.provide(modelServiceKey, makeModelService(makeHttpModelRepository()))
app.mount('#app')
