import { createApp } from 'vue'
import App from './ui/App.vue'
import { router } from './ui/router'
import { modelServiceKey } from './ui/keys'
import { makeModelService } from './application/ModelService'
import { makeHttpModelRepository } from './adapters/http/HttpModelRepository'
import './ui/diagram-types'
import './ui/styles/shared.css'
import { applyThemeChoice, readThemeChoice } from './ui/lib/themePreference'

// Before the first paint, so a reader who chose a theme never sees the other one flash.
applyThemeChoice(readThemeChoice())

const app = createApp(App)
app.use(router)
app.provide(modelServiceKey, makeModelService(makeHttpModelRepository()))
app.mount('#app')
