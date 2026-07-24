import { createRouter, createWebHistory } from 'vue-router';
import App from '../App.vue';
import Settings from '../views/Settings.vue';
import MiningNLP from '../views/MiningNLP.vue';

const routes = [
  { 
    path: '/', 
    component: App, // 主布局（侧边栏+首页内容）
    children: [
      { 
        path: 'settings', 
        component: Settings, 
        meta: { 
          showSidebar: false,
          fullscreen: true,  // 确保启用全屏
          hideChat: true    // 标记为隐藏对话框
        } // 设置页隐藏侧边栏
      },
      {
        path: 'mining-nlp',
        name: 'MiningNLP',
        component: MiningNLP,
        meta: {
          showSidebar: false,
          fullscreen: true, 
          hideChat: true
        }
      }
    ]
  },
  {
    path: '/favorites',
    name: 'Favorites',
    component: () => import('@/views/Favorites.vue')
  },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

export default router;