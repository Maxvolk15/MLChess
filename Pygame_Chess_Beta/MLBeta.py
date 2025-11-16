import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
from ChessBoard import ChessBoard
import random
from collections import deque
import os

class ChessNet(nn.Module):
    def __init__(self):
        super(ChessNet, self).__init__()
        self.conv1 = nn.Conv2d(12, 64, kernel_size=3, padding=1)
        self.conv2 = nn.Conv2d(64, 128, kernel_size=3, padding=1)
        self.conv3 = nn.Conv2d(128, 256, kernel_size=3, padding=1)
        
        self.fc1 = nn.Linear(256 * 8 * 8, 512)
        self.fc2 = nn.Linear(512, 256)
        self.fc3 = nn.Linear(256, 64 * 64)
        
        self.dropout = nn.Dropout(0.3)
        
    def forward(self, x):
        x = torch.relu(self.conv1(x))
        x = torch.relu(self.conv2(x))
        x = torch.relu(self.conv3(x))
        
        x = x.view(-1, 256 * 8 * 8)
        x = torch.relu(self.fc1(x))
        x = self.dropout(x)
        x = torch.relu(self.fc2(x))
        x = self.fc3(x)
        
        return x.view(-1, 64, 64)

def board_to_tensor(board):
    """Convert chess board to tensor for neural network"""
    tensor = torch.zeros(12, 8, 8)
    
    piece_types = {
        'Pawn': 0, 'Knight': 1, 'Bishop': 2,
        'Rook': 3, 'Queen': 4, 'King': 5
    }
    
    for x in range(8):
        for y in range(8):
            piece = board.board[x][y]
            if piece:
                channel = piece_types[piece.name]
                if piece.color == 'b':
                    channel += 6
                tensor[channel, x, y] = 1
                
    return tensor.unsqueeze(0)

class ChessAITrainer:
    def __init__(self, model_path=None):
        self.model = ChessNet()
        self.optimizer = optim.Adam(self.model.parameters(), lr=0.001)
        self.criterion = nn.MSELoss()
        self.memory = deque(maxlen=10000)
        
        if model_path and os.path.exists(model_path):
            self.model.load_state_dict(torch.load(model_path))
        
    def get_random_move(self, board):
        """Get random move for exploration"""
        possible_moves = {}
        for piece in board.get_curr_player_pieces():
            moves = board.get_poss_moves_for(piece)
            if moves:
                possible_moves[piece.position] = moves
        
        if not possible_moves:
            return None
            
        # Choose random piece and random move
        from_pos = random.choice(list(possible_moves.keys()))
        to_pos = random.choice(possible_moves[from_pos])
        return (from_pos, to_pos)
    
    def simulate_game(self):
        """Simulate one game and return game history"""
        board = ChessBoard()
        game_history = []
        
        move_count = 0
        max_moves = 100  # Prevent infinite games
        
        while move_count < max_moves:
            # 80% chance to use random move, 20% to use network (for exploration)
            if random.random() < 0.8:
                move = self.get_random_move(board)
            else:
                move = self.get_network_move(board)
                
            if not move:
                break
                
            from_pos, to_pos = move
            piece = board.get_piece_at(from_pos)
            
            # Store game state and move
            game_history.append((
                board_to_tensor(board).clone(),
                from_pos,
                to_pos,
                board.curr_player
            ))
            
            # Execute move
            captured_piece = board.move_piece(piece, to_pos)
            
            # Pawn promotion
            if piece.name == 'Pawn' and (to_pos[1] == 0 or to_pos[1] == 7):
                from pieces.Queen import Queen
                board.board[to_pos[0]][to_pos[1]] = Queen(board.curr_player, to_pos)
            
            # Switch player
            board.curr_player = 'w' if board.curr_player == 'b' else 'b'
            move_count += 1
            
            # Check for game end
            if self.is_checkmate(board) or move_count >= max_moves:
                break
        
        return game_history
    
    def get_network_move(self, board):
        """Get move using neural network"""
        board_tensor = board_to_tensor(board)
        with torch.no_grad():
            move_probs = self.model(board_tensor)
        
        possible_moves = {}
        for piece in board.get_curr_player_pieces():
            moves = board.get_poss_moves_for(piece)
            if moves:
                possible_moves[piece.position] = moves
        
        move_scores = {}
        for from_pos in possible_moves:
            for to_pos in possible_moves[from_pos]:
                from_idx = from_pos[0] * 8 + from_pos[1]
                to_idx = to_pos[0] * 8 + to_pos[1]
                score = move_probs[0, from_idx, to_idx].item()
                move_scores[(from_pos, to_pos)] = score
        
        if not move_scores:
            return None
            
        best_move = max(move_scores, key=move_scores.get)
        return best_move
    
    def is_checkmate(self, board):
        """Check if current player is in checkmate"""
        for piece in board.get_curr_player_pieces():
            if board.get_poss_moves_for(piece):
                return False
        return True
    
    def train(self, num_games=1000, batch_size=32, save_interval=100):
        """Train the model through self-play"""
        print("Starting training...")
        
        for game_num in range(num_games):
            game_history = self.simulate_game()
            
            if len(game_history) > 0:
                self.update_model(game_history, batch_size)
            
            if game_num % save_interval == 0:
                torch.save(self.model.state_dict(), f'chess_model_{game_num}.pth')
                print(f"Game {game_num} completed and model saved")
            
            if game_num % 10 == 0:
                print(f"Played {game_num} games")
        
        # Save final model
        torch.save(self.model.state_dict(), 'chess_model_final.pth')
        print("Training completed!")
    
    def update_model(self, game_history, batch_size):
        """Update model weights based on game history"""
        if len(self.memory) < batch_size:
            # Add current game to memory
            for state, from_pos, to_pos, player in game_history:
                # Simple reward: +1 for white moves, -1 for black moves
                reward = 1.0 if player == 'w' else -1.0
                self.memory.append((state, from_pos, to_pos, reward))
            return
        
        # Sample batch from memory
        batch = random.sample(self.memory, min(batch_size, len(self.memory)))
        
        states = torch.cat([item[0] for item in batch])
        from_positions = [item[1] for item in batch]
        to_positions = [item[2] for item in batch]
        rewards = torch.tensor([item[3] for item in batch], dtype=torch.float32)
        
        # Prepare target values
        target_output = torch.zeros(len(batch), 64, 64)
        for i, (from_pos, to_pos, reward) in enumerate(zip(from_positions, to_positions, rewards)):
            from_idx = from_pos[0] * 8 + from_pos[1]
            to_idx = to_pos[0] * 8 + to_pos[1]
            target_output[i, from_idx, to_idx] = reward
        
        # Training step
        self.optimizer.zero_grad()
        output = self.model(states)
        loss = self.criterion(output, target_output)
        loss.backward()
        self.optimizer.step()

if __name__ == "__main__":
    trainer = ChessAITrainer()
    trainer.train(num_games=500)  # Train for * games