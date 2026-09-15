import type { RouteRecordRaw } from 'vue-router';

const routes: RouteRecordRaw[] = [
  {
    meta: {
      icon: 'lucide:layout-dashboard',
      order: 0,
      title: '仪表盘',
    },
    name: 'Dashboard',
    path: '/dashboard',
    component: () => import('#/views/dashboard/index.vue'),
  },
  {
    meta: {
      icon: 'lucide:images',
      order: 1,
      title: '图元信息',
    },
    name: 'Gallery',
    path: '/gallery',
    component: () => import('#/views/gallery/index.vue'),
  },
  {
    meta: {
      icon: 'lucide:cloud-upload',
      order: 2,
      title: '上传图片',
    },
    name: 'Upload',
    path: '/upload',
    component: () => import('#/views/upload/index.vue'),
  },
  {
    meta: {
      hideInTab: true,
      icon: 'lucide:user-cog',
      order: 3,
      title: '个人中心',
    },
    name: 'Profile',
    path: '/profile',
    component: () => import('#/views/profile/index.vue'),
  },
];

export default routes;
