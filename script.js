const form = document.getElementById('questionForm');
const questionInput = document.getElementById('questionInput');
const tableBody = document.querySelector('#questionsTable tbody');

let data = [];

form.addEventListener('submit', function(e) {
  e.preventDefault();
  const question = questionInput.value.trim();
  if (question) {
    data.push({ question, answer: '' });
    saveData();
    renderTable();
    questionInput.value = '';
  }
});

function saveData() {
  localStorage.setItem('qa_data', JSON.stringify(data));
}

function loadData() {
  const stored = localStorage.getItem('qa_data');
  if (stored) {
    data = JSON.parse(stored);
  }
}

function renderTable() {
  tableBody.innerHTML = '';
  data.forEach((item, index) => {
    const row = document.createElement('tr');

    const questionCell = document.createElement('td');
    questionCell.textContent = item.question;

    const answeredCell = document.createElement('td');
    answeredCell.textContent = item.answer.trim() ? '✔️' : '❌';

    const answerCell = document.createElement('td');
    const answerInput = document.createElement('input');
    answerInput.type = 'text';
    answerInput.placeholder = 'أدخل الإجابة';
    answerInput.value = item.answer;
    answerInput.addEventListener('input', function () {
      data[index].answer = answerInput.value;
      saveData();
      answeredCell.textContent = answerInput.value.trim() ? '✔️' : '❌';
    });
    answerCell.appendChild(answerInput);

    const deleteCell = document.createElement('td');
    const deleteBtn = document.createElement('button');
    deleteBtn.textContent = '🗑️';
    deleteBtn.style.color = 'red';
    deleteBtn.style.cursor = 'pointer';
    deleteBtn.addEventListener('click', function () {
      data.splice(index, 1);
      saveData();
      renderTable();
    });
    deleteCell.appendChild(deleteBtn);

    row.appendChild(questionCell);
    row.appendChild(answeredCell);
    row.appendChild(answerCell);
    row.appendChild(deleteCell);

    tableBody.appendChild(row);
  });
}

// عند تشغيل الصفحة
loadData();
renderTable();
