<template>
  <div class="favorites-container">
    <h2 class="favorites-title">我的收藏</h2>
    <div class="favorites-list">
      <div v-for="(fav, index) in favorites" :key="index" class="favorite-item">
        <div class="favorite-content">
          {{ fav.text }}
        </div>
        <div class="favorite-actions">
          <el-button type="text" @click="copyFavorite(fav.text)">
            <el-icon><DocumentCopy /></el-icon>
            <span>复制</span>
          </el-button>
          <el-button type="text" @click="removeFavorite(index)" style="color: #F56C6C;">
            <el-icon><Delete /></el-icon>
            <span>删除</span>
          </el-button>
        </div>
      </div>
      <div v-if="favorites.length === 0" class="empty-favorites">
        暂无收藏内容
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { ElMessage } from 'element-plus';
import { DocumentCopy, Delete } from '@element-plus/icons-vue';

const favorites = ref([]);

// 从本地存储加载收藏
onMounted(() => {
  const savedFavorites = localStorage.getItem('aiFavorites');
  if (savedFavorites) {
    favorites.value = JSON.parse(savedFavorites);
  }
});

function copyFavorite(text) {
  navigator.clipboard.writeText(text)
    .then(() => {
      ElMessage.success('已复制到剪贴板');
    })
    .catch(() => {
      ElMessage.error('复制失败');
    });
}

function removeFavorite(index) {
  favorites.value.splice(index, 1);
  localStorage.setItem('aiFavorites', JSON.stringify(favorites.value));
  ElMessage.success('已删除收藏');
}
</script>

<style scoped>
.favorites-container {
  padding: 20px;
  max-width: 900px;
  margin: 0 auto;
}

.favorites-title {
  font-size: 24px;
  margin-bottom: 20px;
  color: #222831;
}

.favorites-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.favorite-item {
  background: #fff;
  border-radius: 8px;
  padding: 16px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.favorite-content {
  margin-bottom: 12px;
  line-height: 1.6;
}

.favorite-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.empty-favorites {
  text-align: center;
  color: #999;
  padding: 40px 0;
}
</style>
