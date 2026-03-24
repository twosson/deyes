import { defineStore } from 'pinia'

export const useUiStore = defineStore('ui', {
  state: () => ({
    siderCollapsed: false,
  }),
  actions: {
    setSiderCollapsed(value: boolean) {
      this.siderCollapsed = value
    },
    toggleSider() {
      this.siderCollapsed = !this.siderCollapsed
    },
  },
})
