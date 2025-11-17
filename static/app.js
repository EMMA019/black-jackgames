document.addEventListener('DOMContentLoaded', () => {
    // --- 1. SocketIOとDOM要素の初期化 ---
    const socket = io();
    
    // スクリーン
    const screens = {
        loading: document.getElementById('loading-screen'),
        lobby: document.getElementById('lobby-screen'),
        game: document.getElementById('game-screen'),
    };
    
    // ロビー要素
    const lobby = {
        difficultySelect: document.getElementById('difficulty-select'),
        betAmountInput: document.getElementById('bet-amount'),
        lobbyBalance: document.getElementById('lobby-balance'),
        startBtn: document.getElementById('start-game-btn'),
        resetBtn: document.getElementById('reset-game-btn'),
    };

    // ゲームテーブル要素
    const game = {
        dealer: {
            name: document.getElementById('dealer-name'),
            hand: document.getElementById('dealer-hand'),
            score: document.getElementById('dealer-score'),
        },
        ai: {
            name: document.getElementById('ai-name'),
            hand: document.getElementById('ai-hand'),
            score: document.getElementById('ai-score'),
            thinking: document.getElementById('ai-thinking'),
        },
        player: {
            name: document.getElementById('player-name'),
            hand: document.getElementById('player-hand'),
            score: document.getElementById('player-score'),
            balance: document.getElementById('player-balance'),
            bet: document.getElementById('player-bet'),
        },
        message: document.getElementById('game-message'),
        winnerMessage: document.getElementById('winner-message'),
        betControls: document.getElementById('bet-controls'),
        actionControls: document.getElementById('action-controls'),
        nextBetAmount: document.getElementById('next-bet-amount'),
        nextRoundBtn: document.getElementById('next-round-btn'),
        hitBtn: document.getElementById('hit-btn'),
        standBtn: document.getElementById('stand-btn'),
    };

    // エラートースト
    const errorToast = document.getElementById('error-toast');
    const errorMessage = document.getElementById('error-message');
    let errorTimer;

    // --- 2. ユーティリティ関数 ---

    /**
     * 指定されたスクリーンを表示し、他を隠す
     * @param {string} screenName 'loading', 'lobby', 'game'
     */
    function showScreen(screenName) {
        Object.keys(screens).forEach(key => {
            if (key === screenName) {
                screens[key].classList.remove('hidden');
                screens[key].style.display = 'flex'; // 'hidden' が 'display: none' を設定するため
            } else {
                screens[key].classList.add('hidden');
            }
        });
    }

    /**
     * エラートーストを表示する
     * @param {string} message 
     */
    function showError(message) {
        errorMessage.textContent = message;
        errorToast.classList.remove('hidden');
        
        clearTimeout(errorTimer);
        errorTimer = setTimeout(() => {
            errorToast.classList.add('hidden');
        }, 3000);
    }

    /**
     * カードのHTMLを生成する (仕様書 3.2 UX/アニメーション)
     * @param {object} card { suit: 'Hearts', rank: 'K' }
     */
    function createCardElement(card) {
        const cardEl = document.createElement('div');
        cardEl.classList.add('card', `suit-${card.suit}`);
        
        const rank = document.createElement('span');
        rank.classList.add('card-rank');
        rank.textContent = card.rank;
        
        const suit = document.createElement('span');
        suit.classList.add('card-suit');
        suit.textContent = getSuitSymbol(card.suit);

        if (card.suit === 'Hidden') {
            rank.textContent = '';
            suit.textContent = '';
        }

        cardEl.appendChild(rank);
        cardEl.appendChild(suit);
        return cardEl;
    }

    function getSuitSymbol(suit) {
        switch (suit) {
            case 'Hearts': return '♥';
            case 'Diamonds': return '♦';
            case 'Clubs': return '♣';
            case 'Spades': return '♠';
            default: return '';
        }
    }

    /**
     * 手札を描画する
     * @param {HTMLElement} handElement 
     * @param {Array} cards 
     */
    function renderHand(handElement, cards) {
        handElement.innerHTML = ''; // 一旦クリア
        cards.forEach(card => {
            handElement.appendChild(createCardElement(card));
        });
    }

    // --- 3. SocketIO イベントリスナー (Server -> Client) ---

    socket.on('connect', () => {
        console.log('Connected to server.');
        // 'connect' 時に 'awaiting_start' が
        // emitされるか、'game_state_update' が emit される
    });

    socket.on('disconnect', () => {
        showError('Disconnected from server. Trying to reconnect...');
        showScreen('loading');
    });

    socket.on('awaiting_start', (data) => {
        console.log(data.message);
        showScreen('lobby');
        // TODO: lobbyBalance をDBから取得するロジック (今は 'game_state_update' に依存)
        // 簡易的にデフォルト値を設定
        lobby.lobbyBalance.textContent = '1000';
    });

    /**
     * メインのゲーム状態更新 (仕様書 4. API)
     */
    socket.on('game_state_update', (state) => {
        console.log('Game state update:', state);

        // --- どのスクリーンを表示するか判断 ---
        if (state.phase === 'waiting_for_bet') {
            showScreen('lobby');
            lobby.lobbyBalance.textContent = state.player.balance;
        } else {
            showScreen('game');
        }

        // --- 共通の残高表示を更新 ---
        lobby.lobbyBalance.textContent = state.player.balance;
        game.player.balance.textContent = state.player.balance;
        game.player.bet.textContent = state.player.current_bet;
        game.nextBetAmount.value = 50; // ベット額をリセット

        // --- ゲームテーブルの情報を更新 ---
        renderHand(game.dealer.hand, state.dealer.hand);
        game.dealer.score.textContent = `Score: ${state.dealer.score}`;

        renderHand(game.ai.hand, state.ai_player.hand);
        game.ai.score.textContent = `Score: ${state.ai_player.score}`;

        renderHand(game.player.hand, state.player.hand);
        game.player.score.textContent = `Score: ${state.player.score}`;

        // --- UIの状態制御 ---
        game.message.textContent = getPhaseMessage(state.phase);
        game.ai.thinking.classList.toggle('hidden', state.phase !== 'ai_turn');
        game.actionControls.classList.toggle('hidden', !state.can_hit_stand);
        
        // ▼▼▼ 修正ブロック (不整合の修正) ▼▼▼
        
        // 勝者メッセージ (仕様書 3.2 UX/アニメーション: 勝敗エフェクト)
        if (state.phase === 'round_end') {
            game.winnerMessage.textContent = `Winner: ${state.last_round_winner}!`;
            game.winnerMessage.classList.remove('hidden');
        } else {
            game.winnerMessage.classList.add('hidden');
        }
        
        // ゲームオーバーとベット制御のロジックを統合
        if (state.is_game_over) {
            game.message.textContent = 'GAME OVER. You have no money!';
            game.betControls.classList.remove('hidden'); // 表示
            game.nextRoundBtn.textContent = 'Play Again (Reset)';
        } else if (state.can_bet) {
            // (ROUND_END または WAITING_FOR_BET)
            game.betControls.classList.remove('hidden'); // 表示
            game.nextRoundBtn.textContent = 'Place Bet (Next Round)';
        } else {
            // (DEALING, PLAYER_TURN, AI_TURN, DEALER_TURN)
            game.betControls.classList.add('hidden'); // 非表示
        }
        // ▲▲▲ 修正ブロック ▲▲▲
    });

    socket.on('game_over', (data) => {
        showError(data.message);
        // game_state_update が is_game_over: true で来るはず
    });

    socket.on('error', (data) => {
        showError(data.message);
    });

    function getPhaseMessage(phase) {
        switch (phase) {
            case 'waiting_for_bet': return 'Place your bet to start the game.';
            case 'dealing': return 'Dealing cards...';
            case 'player_turn': return 'Your turn: Hit or Stand?';
            case 'ai_turn': return 'AI is thinking...';
            case 'dealer_turn': return "Dealer's turn...";
            case 'round_end': return 'Round over. Place your next bet.';
            case 'game_over': return 'GAME OVER. Reset to play again.';
            default: return '';
        }
    }

    // --- 4. UI イベントリスナー (Client -> Server) ---

    // 3.1. ロビー画面
    lobby.startBtn.addEventListener('click', () => {
        const data = {
            difficulty: lobby.difficultySelect.value,
            bet_amount: parseInt(lobby.betAmountInput.value, 10),
        };
        if (data.bet_amount <= 0) {
            showError('Bet amount must be positive.');
            return;
        }
        console.log('Emitting start_game:', data);
        socket.emit('start_game', data);
    });

    lobby.resetBtn.addEventListener('click', () => {
        if (confirm('Are you sure you want to reset your game? Your balance will be reset to $1000.')) {
            console.log('Emitting reset_game');
            socket.emit('reset_game');
        }
    });

    // 3.2. ゲームテーブル画面
    game.hitBtn.addEventListener('click', () => {
        socket.emit('player_action', { action: 'hit' });
    });

    game.standBtn.addEventListener('click', () => {
        socket.emit('player_action', { action: 'stand' });
    });

    game.nextRoundBtn.addEventListener('click', () => {
        const bet_amount = parseInt(game.nextBetAmount.value, 10);
        if (bet_amount <= 0) {
            showError('Bet amount must be positive.');
            return;
        }
        
        const data = {
            difficulty: lobby.difficultySelect.value, // 難易度はロビーの選択を維持
            bet_amount: bet_amount,
        };
        
        // ゲームオーバーからのリスタート
        if (game.nextRoundBtn.textContent.includes('Play Again')) {
            console.log('Emitting reset_game (from Game Over)');
            // reset_game は残高を1000に戻し、'waiting_for_bet' にする
            socket.emit('reset_game'); 
            // reset_game が完了すると 'game_state_update' が来て lobby に戻る
        } else {
            console.log('Emitting start_game (next round):', data);
            socket.emit('start_game', data);
        }
    });

    // --- 5. 初期化実行 ---
    showScreen('loading');
    // 'connect' イベントが発火すると、'awaiting_start' か
    // 'game_state_update' が来て、適切なスクリーンが表示される
});