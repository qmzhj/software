// ---------- 共享用户详情弹窗 ----------
let memberInfoTarget = null;

async function showMemberInfo(el) {
  const uid = el.dataset ? el.dataset.uid : el;
  const name = el.dataset ? (el.dataset.name || '') : '';
  const role = el.dataset ? (el.dataset.role || '') : '';
  memberInfoTarget = { uid, name, role: role || '' };

  document.getElementById("memberInfoAvatar").textContent = name.charAt(0);
  document.getElementById("memberInfoName").textContent = name;
  document.getElementById("memberInfoUid").textContent = uid;
  const roleMap = { 'student': '学生', 'teacher': '教师', 'manager': '管理员' };
  document.getElementById("memberInfoRole").textContent = roleMap[role] || role || '';

  try {
    const userData = await api('/api/user/' + uid);
    document.getElementById("memberInfoDesc").textContent = userData.description || '暂无简介';
  } catch (e) {
    document.getElementById("memberInfoDesc").textContent = '暂无简介';
  }

  // Load and display tags
  const tagsContainer = document.getElementById("memberInfoTags");
  if (tagsContainer) {
    tagsContainer.innerHTML = '';
    try {
      const tags = await api('/api/user/' + uid + '/tags');
      if (tags && tags.length) {
        tagsContainer.innerHTML = tags.map(t =>
          '<span style="background:#eef2ff;color:#4f46e5;padding:2px 8px;border-radius:10px;font-size:12px;">' + escapeHtml(t.label) + '</span>'
        ).join('');
      }
    } catch (e) { /* tags not available */ }
  }

  if (typeof updateFriendBtn === 'function') updateFriendBtn();
  if (typeof updateBlockBtn === 'function') updateBlockBtn();
  if (typeof renderPrivateCallNotifyToggle === 'function') renderPrivateCallNotifyToggle();

  showModal('memberInfoModal');
}

async function memberInfoStartChat() {
  if (!memberInfoTarget) return;
  const uid = memberInfoTarget.uid;
  const name = memberInfoTarget.name;
  if (typeof openPopupChat === 'function') {
    openPopupChat(uid, name);
  }
}
