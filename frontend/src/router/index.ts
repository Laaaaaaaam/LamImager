import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'sessions',
      component: () => import('../views/Sessions.vue'),
    },
    {
      path: '/dashboard',
      name: 'dashboard',
      component: () => import('../views/Dashboard.vue'),
    },
    {
      path: '/api-manage',
      name: 'api-manage',
      component: () => import('../views/ApiManage.vue'),
    },
    {
      path: '/skills',
      name: 'skills',
      component: () => import('../views/SkillManage.vue'),
    },
    {
      path: '/rules',
      name: 'rules',
      component: () => import('../views/RuleManage.vue'),
    },
    {
      path: '/references',
      name: 'references',
      component: () => import('../views/ReferenceManage.vue'),
    },
    {
      path: '/plan-templates',
      name: 'plan-templates',
      component: () => import('../views/PlanTemplateManage.vue'),
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('../views/Settings.vue'),
    },
  ],
})

export default router
