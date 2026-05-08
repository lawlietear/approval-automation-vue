import { ref, onMounted, onUnmounted, type Ref } from 'vue'

export function useMagnetic(elRef: Ref<HTMLElement | null>, maxOffset = 4, radius = 60) {
  const offset = ref({ x: 0, y: 0 })
  let rafId: number | null = null

  const onMove = (e: MouseEvent) => {
    const el = elRef.value
    if (!el) return
    const rect = el.getBoundingClientRect()
    const centerX = rect.left + rect.width / 2
    const centerY = rect.top + rect.height / 2
    const dx = e.clientX - centerX
    const dy = e.clientY - centerY
    const dist = Math.sqrt(dx * dx + dy * dy)

    if (dist < radius) {
      const pull = (radius - dist) / radius
      offset.value = {
        x: (dx / radius) * maxOffset * pull,
        y: (dy / radius) * maxOffset * pull,
      }
    } else {
      offset.value = { x: 0, y: 0 }
    }
  }

  const onLeave = () => {
    offset.value = { x: 0, y: 0 }
  }

  onMounted(() => {
    window.addEventListener('mousemove', onMove)
    const el = elRef.value
    if (el) el.addEventListener('mouseleave', onLeave)
  })

  onUnmounted(() => {
    window.removeEventListener('mousemove', onMove)
    const el = elRef.value
    if (el) el.removeEventListener('mouseleave', onLeave)
    if (rafId) cancelAnimationFrame(rafId)
  })

  return offset
}
