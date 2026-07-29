import { inject, ref, type Ref } from 'vue'

export const useWriteBlock = (): Ref<boolean> => {
  return inject<Ref<boolean>>('writeBlocked', ref(false))
}
