import { VueQueryPlugin, QueryClient } from '@tanstack/vue-query'
import Antd, { message } from 'ant-design-vue'
import { createPinia } from 'pinia'
import { createApp } from 'vue'

import App from './App.vue'
import { router } from './app/router'
import './styles/global.css'
import 'ant-design-vue/dist/reset.css'

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
})

message.config({
  top: '72px',
  maxCount: 3,
  duration: 2.5,
})

const app = createApp(App)

app.use(createPinia())
app.use(router)
app.use(Antd)
app.use(VueQueryPlugin, { queryClient })
app.mount('#app')
