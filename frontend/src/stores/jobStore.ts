import { create } from 'zustand'

interface JobStore {
  activeJobId: string | null
  isLogOpen: boolean
  setActiveJob: (id: string) => void
  clearActiveJob: () => void
  openLog: () => void
  closeLog: () => void
}

export const useJobStore = create<JobStore>((set) => ({
  activeJobId: null,
  isLogOpen: false,
  setActiveJob: (id) => set({ activeJobId: id, isLogOpen: true }),
  clearActiveJob: () => set({ activeJobId: null, isLogOpen: false }),
  openLog: () => set({ isLogOpen: true }),
  closeLog: () => set({ isLogOpen: false }),
}))
