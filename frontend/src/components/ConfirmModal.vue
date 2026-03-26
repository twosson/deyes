<script setup lang="ts">
interface Props {
  open: boolean
  title: string
  content: string
  okText?: string
  cancelText?: string
  okType?: 'primary' | 'default' | 'danger'
  confirmLoading?: boolean
}

withDefaults(defineProps<Props>(), {
  okText: '确定',
  cancelText: '取消',
  okType: 'primary',
  confirmLoading: false,
})

const emit = defineEmits<{
  'update:open': [value: boolean]
  confirm: []
  cancel: []
}>()

const handleOk = () => {
  emit('confirm')
}

const handleCancel = () => {
  emit('update:open', false)
  emit('cancel')
}
</script>

<template>
  <a-modal
    :open="open"
    :title="title"
    :ok-text="okText"
    :cancel-text="cancelText"
    :ok-type="okType"
    :confirm-loading="confirmLoading"
    @ok="handleOk"
    @cancel="handleCancel"
  >
    <p>{{ content }}</p>
  </a-modal>
</template>
