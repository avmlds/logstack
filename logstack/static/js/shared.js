let debounceTimeout;
let selectedIndex = -1;

function debouncedFetchSuggestions() {
  clearTimeout(debounceTimeout);
  debounceTimeout = setTimeout(fetchSuggestions, 300);
}

async function fetchSuggestions() {
  const prefixInput = document.getElementById('prefix');
  const prefix = prefixInput.value;
  const suggestionsBox = document.getElementById('suggestions');
  if (!prefix) return suggestionsBox.style.display = 'none';

  const res = await fetch('/api/data/prefix-autocomplete?prefix=' + encodeURIComponent(prefix));
  const { result } = await res.json();

  if (!result.length) {
    suggestionsBox.style.display = 'none';
    return;
  }

  suggestionsBox.innerHTML = result.map((item, i) =>
    `<li style="padding: 0.4rem; cursor: pointer;" data-index="${i}" onclick="selectSuggestion('${prefix}${item}')">${prefix}${item}</li>`
  ).join('');
  suggestionsBox.style.display = 'block';
  selectedIndex = -1;
}

function selectSuggestion(value) {
  document.getElementById('prefix').value = value;
  document.getElementById('suggestions').style.display = 'none';
  loadTrends();
}

document.getElementById('prefix').addEventListener('keydown', function(e) {
  const list = document.querySelectorAll('#suggestions li');
  if (!list.length) return;

  if (e.key === 'ArrowDown') {
    e.preventDefault();
    selectedIndex = (selectedIndex + 1) % list.length;
    highlightItem(list, selectedIndex);
  } else if (e.key === 'ArrowUp') {
    e.preventDefault();
    selectedIndex = (selectedIndex - 1 + list.length) % list.length;
    highlightItem(list, selectedIndex);
  } else if (e.key === 'Enter') {
    if (selectedIndex >= 0 && selectedIndex < list.length) {
      e.preventDefault();
      list[selectedIndex].click();
      fetchSuggestions();
    }
  }
});

function highlightItem(list, index) {
  list.forEach(li => li.style.background = '');
  list[index].style.background = '#4e8cff';
}
function hideSuggestionsLater() {
  setTimeout(() => {
    const suggestionsBox = document.getElementById('suggestions');
    suggestionsBox.style.display = 'none';
  }, 150);
}
document.addEventListener('click', function (event) {
  const prefixInput = document.getElementById('prefix');
  const suggestionsBox = document.getElementById('suggestions');
  if (!prefixInput.contains(event.target) && !suggestionsBox.contains(event.target)) {
    suggestionsBox.style.display = 'none';
  }
});
