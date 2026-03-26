<script setup lang="ts">
import { reactive, ref, watch } from 'vue'

import { useCandidatesQuery } from '@/queries/useCandidatesQuery'
import { useCreateExperimentMutation } from '@/queries/useExperimentsQuery'
import { MetricGoal } from '@/types/experiments'

interface Props {
  visible: boolean
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:visible': [value: boolean]
}>()

const candidatesQuery = useCandidatesQuery()
const createMutation = useCreateExperimentMutation()

const formState = reactive({
  name: '',
  candidate_product_id: undefined as string | undefined,
  metric_goal: MetricGoal.CTR as MetricGoal,
  target_platform: undefined as string | undefined,
  region: undefined as string | undefined,
})

const candidateOptions = ref(
  (candidatesQuery.data.value?.items ?? []).map((item) => ({
    value: item.id,
    label: item.title,
  }))
)

watch(
  () => candidatesQuery.data.value,
  (data) => {
    if (data) {
      candidateOptions.value = data.items.map((item) => ({
        value: item.id,
        label: item.title,
      }))
    }
  }
)

async function handleOk() {
  if (!formState.candidate_product_id || !formState.name) {
    return
  }

  await createMutation.mutateAsync({
    candidate_product_id: formState.candidate_product_id,
    name: formState.name,
    metric_goal: formState.metric_goal,
    target_platform: formState.target_platform,
    region: formState.region,
  })

  emit('update:visible', false)
  resetForm()
}

function handleCancel() {
  emit('update:visible', false)
  resetForm()
}

function resetForm() {
  formState.name = ''
  formState.candidate_product_id = undefined
  formState.metric_goal = MetricGoal.CTR
  formState.target_platform = undefined
  formState.region = undefined
}
</script>

<template>
  <a-modal
    :open="visible"
    title="创建A/B测试实验"
    ok-text="创建"
    cancel-text="取消"
    :confirm-loading="createMutation.isPending.value"
    @ok="handleOk"
    @cancel="handleCancel"
  >
    <div class="page-stack">
      <a-form layout="vertical">
        <a-form-item label="实验名称" required>
          <a-input v-model:value="formState.name" placeholder="例如：主图A/B测试 - 白底vs场景" />
        </a-form-item>

        <a-form-item label="商品" required>
          <a-select
            v-model:value="formState.candidate_product_id"
            show-search
            placeholder="选择商品"
            :options="candidateOptions"
            :loading="candidatesQuery.isLoading.value"
          />
        </a-form-item>

        <a-form-item label="目标指标" required>
          <a-select v-model:value="formState.metric_goal" placeholder="选择目标指标">
            <a-select-option :value="MetricGoal.CTR">点击率 (CTR)</a-select-option>
            <a-select-option :value="MetricGoal.CVR">转化率 (CVR)</a-select-option>
            <a-select-option :value="MetricGoal.ORDERS">订单数</a-select-option>
            <a-select-option :value="MetricGoal.REVENUE">收入</a-select-option>
            <a-select-option :value="MetricGoal.UNITS_SOLD">销量</a-select-option>
            <a-select-option :value="MetricGoal.ROAS">广告回报率 (ROAS)</a-select-option>
          </a-select>
        </a-form-item>

        <a-form-item label="目标平台（可选）">
          <a-select
            v-model:value="formState.target_platform"
            allow-clear
            placeholder="选择平台"
          >
            <a-select-option value="temu">Temu</a-select-option>
            <a-select-option value="aliexpress">AliExpress</a-select-option>
            <a-select-option value="amazon">Amazon</a-select-option>
            <a-select-option value="ozon">Ozon</a-select-option>
          </a-select>
        </a-form-item>

        <a-form-item label="目标区域（可选）">
          <a-input v-model:value="formState.region" placeholder="例如：US, UK, DE" />
        </a-form-item>
      </a-form>
    </div>
  </a-modal>
</template>
