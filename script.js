const API_BASE_URL = window.location.origin + '/api';

// Telegram WebApp initialization
let tg = window.Telegram.WebApp;
tg.expand();
tg.ready();

// Global state
let userData = {
    balance: 0,
    deposits: [],
    referrals: { level1: 0, level2: 0, level3: 0 },
    userId: null,
    refLink: ''
};

// Initialize app
document.addEventListener('DOMContentLoaded', function() {
    initializeApp();
    setupEventListeners();
    loadUserData();
});

function initializeApp() {
    // Get user data from Telegram
    if (tg.initDataUnsafe.user) {
        userData.userId = tg.initDataUnsafe.user.id;
        userData.refLink = `https://t.me/your_bot_username?start=ref${userData.userId}`;
        document.getElementById('ref-link').value = userData.refLink;
    }

    // Update payment info based on selected method
    updatePaymentInfo('card');

    // Set initial withdraw balance
    document.getElementById('withdraw-balance').textContent = userData.balance.toFixed(2);
}

function setupEventListeners() {
    // Navigation tabs
    document.querySelectorAll('.nav-tab').forEach(tab => {
        tab.addEventListener('click', function() {
            const tabName = this.getAttribute('data-tab');
            switchTab(tabName);
        });
    });

    // Payment method selection for deposit
    document.querySelectorAll('#deposit .payment-method').forEach(method => {
        method.addEventListener('click', function() {
            const methodName = this.getAttribute('data-method');
            selectPaymentMethod('deposit', methodName);
            updatePaymentInfo(methodName);
        });
    });

    // Payment method selection for withdraw
    document.querySelectorAll('#withdraw .payment-method').forEach(method => {
        method.addEventListener('click', function() {
            const methodName = this.getAttribute('data-method');
            selectPaymentMethod('withdraw', methodName);
        });
    });

    // Close modal on backdrop click
    document.getElementById('invest-modal').addEventListener('click', function(e) {
        if (e.target === this) {
            closeModal();
        }
    });
}

function switchTab(tabName) {
    // Update active tab
    document.querySelectorAll('.nav-tab').forEach(tab => {
        tab.classList.remove('active');
    });
    document.querySelector(`[data-tab="${tabName}"]`).classList.add('active');

    // Update active content
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById(tabName).classList.add('active');
}

function selectPaymentMethod(type, method) {
    const selector = `#${type} .payment-method`;
    document.querySelectorAll(selector).forEach(m => {
        m.classList.remove('active');
    });
    document.querySelector(`#${type} [data-method="${method}"]`).classList.add('active');
}

function updatePaymentInfo(method) {
    const paymentInfo = document.getElementById('payment-info');
    let content = '';

    switch(method) {
        case 'card':
            content = `
                <h4>💳 Банковская карта</h4>
                <p>Номер карты: <span class="highlight">5536 9137 2845 9012</span></p>
                <p>Получатель: <span class="highlight">Алексей Петров</span></p>
                <p>⏰ Обработка: до 15 минут</p>
                <p>💰 Минимум: 100 RUB</p>
            `;
            break;
        case 'sbp':
            content = `
                <h4>📱 Система быстрых платежей</h4>
                <p>Номер телефона: <span class="highlight">+7 912 345 67 89</span></p>
                <p>Получатель: <span class="highlight">Иван Иванов</span></p>
                <p>⏰ Обработка: до 5 минут</p>
                <p>💰 Минимум: 100 RUB</p>
            `;
            break;
        case 'crypto':
            content = `
                <h4>₿ Криптовалюта</h4>
                <p>USDT (TRC20): <span class="highlight">TBvZ1K4bLjLQ9Q7x8Jz3kPqA2nW5rRtYy</span></p>
                <p>⚠️ Только USDT в сети TRC20!</p>
                <p>⏰ Обработка: до 30 минут</p>
                <p>💰 Минимум: 500 RUB</p>
            `;
            break;
    }

    paymentInfo.innerHTML = content;
}

function setAmount(amount) {
    document.getElementById('deposit-amount').value = amount;
}

function showInvestModal() {
    document.getElementById('invest-modal').classList.add('active');
    document.body.style.overflow = 'hidden';
}

function closeModal() {
    document.getElementById('invest-modal').classList.remove('active');
    document.body.style.overflow = 'auto';
}

function showLoading() {
    document.getElementById('loading').classList.add('active');
}

function hideLoading() {
    document.getElementById('loading').classList.remove('active');
}

function showToast(message, type = 'info') {
    const toast = document.getElementById('toast');
    toast.textContent = message;
    toast.className = `toast ${type} show`;

    setTimeout(() => {
        toast.classList.remove('show');
    }, 3000);
}

async function submitDeposit() {
    const amount = parseFloat(document.getElementById('deposit-amount').value);
    const method = document.querySelector('#deposit .payment-method.active').getAttribute('data-method');

    if (!amount || amount < 100) {
        showToast('Минимальная сумма пополнения: 100 RUB', 'error');
        return;
    }

    if (method === 'crypto' && amount < 500) {
        showToast('Минимальная сумма для криптовалюты: 500 RUB', 'error');
        return;
    }

    const data = {
        action: 'deposit',
        amount: amount,
        method: method,
        userId: userData.userId
    };

    // Отправляем данные боту
    tg.sendData(JSON.stringify(data));
    tg.close();
}
async function submitWithdraw() {
    const amount = parseFloat(document.getElementById('withdraw-amount').value);
    const requisites = document.getElementById('withdraw-requisites').value.trim();
    const method = document.querySelector('#withdraw .payment-method.active').getAttribute('data-method');

    if (!amount || amount < 100) {
        showToast('Минимальная сумма вывода: 100 RUB', 'error');
        return;
    }

    if (!requisites || requisites.length < 5) {
        showToast('Введите корректные реквизиты', 'error');
        return;
    }

    if (amount > userData.balance) {
        showToast('Недостаточно средств на балансе', 'error');
        return;
    }

    const data = {
        action: 'withdraw',
        amount: amount,
        method: method,
        requisites: requisites,
        userId: userData.userId
    };

    // Отправляем данные боту
    tg.sendData(JSON.stringify(data));
    tg.close();
}

async function submitInvestment() {
    const amount = parseFloat(document.getElementById('invest-amount').value);

    if (!amount || amount < 10) {
        showToast('Минимальная сумма инвестиций: 10 RUB', 'error');
        return;
    }

    if (amount > userData.balance) {
        showToast('Недостаточно средств на балансе', 'error');
        return;
    }

    const data = {
        action: 'invest',
        amount: amount,
        userId: userData.userId
    };

    // Отправляем данные боту
    tg.sendData(JSON.stringify(data));
    tg.close();
}

async function submitWithdraw() {
    const amount = parseFloat(document.getElementById('withdraw-amount').value);
    const requisites = document.getElementById('withdraw-requisites').value.trim();
    const method = document.querySelector('#withdraw .payment-method.active').getAttribute('data-method');

    if (!amount || amount < 100) {
        showToast('Минимальная сумма вывода: 100 RUB', 'error');
        return;
    }

    if (!requisites || requisites.length < 5) {
        showToast('Введите корректные реквизиты', 'error');
        return;
    }

    if (amount > userData.balance) {
        showToast('Недостаточно средств на балансе', 'error');
        return;
    }

    showLoading();

    try {
        // Send data to bot
        const data = {
            action: 'withdraw',
            amount: amount,
            method: method,
            requisites: requisites,
            userId: userData.userId
        };

        // Simulate API call
        await simulateApiCall();

        showToast('Заявка на вывод создана! Ожидайте обработки.', 'success');
        document.getElementById('withdraw-amount').value = '';
        document.getElementById('withdraw-requisites').value = '';

        // Send data to Telegram bot
        tg.sendData(JSON.stringify(data));

    } catch (error) {
        showToast('Произошла ошибка при создании заявки', 'error');
    } finally {
        hideLoading();
    }
}


function copyLink() {
    const refLink = document.getElementById('ref-link');
    refLink.select();
    refLink.setSelectionRange(0, 99999);

    navigator.clipboard.writeText(refLink.value).then(() => {
        showToast('Ссылка скопирована в буфер обмена!', 'success');
    }).catch(() => {
        showToast('Не удалось скопировать ссылку', 'error');
    });
}

function shareLink() {
    const shareText = `🚀 Присоединяйся к TON STOCKER!\n💰 Стабильный доход 4% в день\n🎁 Получи бонус по моей ссылке:\n${userData.refLink}`;

    if (navigator.share) {
        navigator.share({
            title: 'TON STOCKER',
            text: shareText
        });
    } else {
        // Fallback for Telegram
        tg.openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(userData.refLink)}&text=${encodeURIComponent(shareText)}`);
    }
}

async function loadUserData() {
    showLoading();

    try {
        // Simulate loading user data
        await simulateApiCall();

        // Mock data - replace with actual API call
        userData = {
            ...userData,
            balance: 1250.50,
            deposits: [
                { amount: 1000, startDate: '2025-09-20T10:00:00Z', profit: 120.50 },
                { amount: 500, startDate: '2025-09-25T15:30:00Z', profit: 45.20 }
            ],
            referrals: { level1: 5, level2: 12, level3: 3 }
        };

        updateUI();

    } catch (error) {
        showToast('Ошибка загрузки данных', 'error');
    } finally {
        hideLoading();
    }
}

function updateUI() {
    // Update balance
    document.querySelector('.user-balance').textContent = `₽${userData.balance.toFixed(2)}`;
    document.getElementById('balance').textContent = userData.balance.toFixed(2);
    document.getElementById('withdraw-balance').textContent = userData.balance.toFixed(2);

    // Update stats
    const totalInvested = userData.deposits.reduce((sum, dep) => sum + dep.amount, 0);
    const currentProfit = userData.deposits.reduce((sum, dep) => sum + dep.profit, 0);

    document.getElementById('total-invested').textContent = totalInvested.toFixed(2);
    document.getElementById('current-profit').textContent = currentProfit.toFixed(2);
    document.getElementById('deposits-count').textContent = userData.deposits.length;

    // Update referrals
    document.getElementById('referrals-count').textContent =
        userData.referrals.level1 + userData.referrals.level2 + userData.referrals.level3;
    document.getElementById('ref-level1').textContent = userData.referrals.level1;
    document.getElementById('ref-level2').textContent = userData.referrals.level2;
    document.getElementById('ref-level3').textContent = userData.referrals.level3;

    // Update deposits list
    updateDepositsList();
}

function updateDepositsList() {
    const depositsList = document.getElementById('deposits-list');

    if (userData.deposits.length === 0) {
        depositsList.innerHTML = `
            <div class="empty-state">
                <p>У вас пока нет активных депозитов</p>
                <button class="btn btn-outline" onclick="showInvestModal()">Создать депозит</button>
            </div>
        `;
        return;
    }

    depositsList.innerHTML = userData.deposits.map(deposit => `
        <div class="deposit-item slide-up">
            <div class="deposit-info">
                <h4>Депозит ₽${deposit.amount.toFixed(2)}</h4>
                <p>Дата создания: ${new Date(deposit.startDate).toLocaleDateString('ru-RU')}</p>
                <p>Доходность: 4% в день</p>
            </div>
            <div class="deposit-profit">
                <div class="profit-amount">+₽${deposit.profit.toFixed(2)}</div>
                <p>Прибыль</p>
            </div>
        </div>
    `).join('');
}

function simulateApiCall() {
    return new Promise(resolve => {
        setTimeout(resolve, 1500);
    });
}

// Handle Telegram WebApp events
tg.onEvent('mainButtonClicked', function() {
    tg.close();
});

tg.onEvent('backButtonClicked', function() {
    if (document.getElementById('invest-modal').classList.contains('active')) {
        closeModal();
    } else {
        tg.close();
    }
});

// Set main button
tg.MainButton.setText('Закрыть');
tg.MainButton.show();

// Show back button when modal is open
function showInvestModal() {
    document.getElementById('invest-modal').classList.add('active');
    document.body.style.overflow = 'hidden';
    tg.BackButton.show();
}

function closeModal() {
    document.getElementById('invest-modal').classList.remove('active');
    document.body.style.overflow = 'auto';
    tg.BackButton.hide();
}

