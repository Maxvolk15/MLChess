import pygame
from pygame.locals import *
import time
from pieces.Queen import Queen
from ChessBoard import ChessBoard

from ML import EngineAI, DirectionRules


class Game:
    def __init__(self, ai_enabled=False, engine_path=None):
        pygame.init()
        self.game_display = pygame.display.set_mode((600, 600))
        pygame.display.set_caption('Chess')

        self.settings = {'board_image': 'images/board.png'}
        self.board_image = pygame.image.load(self.settings['board_image'])

        self.clock = pygame.time.Clock()

        # сначала создаём доску
        self.chess_board = ChessBoard()

        # остальное состояние игры
        self.curr_selected_piece = None
        self.curr_poss_moves = []
        self.all_poss_moves = self.get_all_poss_moves()

        # флаги AI
        self.ai_enabled = ai_enabled
        self.ai_thinking = False

        # rules (если используем) (dx, dy)
        # “Односторонний мир”: AI может ходить только вниз (для чёрных) + диагональ вниз. (0, -1), (1, -1), (-1, -1)
        # “Только горизонталь”: разрешены (±1,0) — AI гоняет фигуры по линиям.
        # “Только диагонали”: разрешены (±1,±1) — кидает по диагоналям.
        # “Запрет отступления”: для чёрных запрещаем dy>0 (нельзя “назад”), для белых запрещаем dy<0.
        # Персональные правила по типу фигуры: пешкам одно, слонам другое (можно расширить в DirectionRules.is_allowed()).

        # self.ai_rules_black = DirectionRules(
        #     allowed_vectors={(0, -1), (-1, 0), (1, 0), (-1, -1), (1, -1)},
        #     allow_knight=True
        # )
        self.ai_rules_black = None
        self.ai_rules_white = None

        # Массивы для фото фигур
        self.white_pieces_taken_images = []
        self.black_pieces_taken_images = []

        # движок
        self.ai = EngineAI(engine_path, movetime_ms=150) if (ai_enabled and engine_path) else None

        # запускаем цикл
        self.play_game()

    def play_game(self):
        """Цикл игры"""
        while True:
            # Ход ИИ
            if (self.ai_enabled and self.chess_board.curr_player == 'b' and not self.ai_thinking):
                self.ai_thinking = True
                self.make_ai_move()
                self.ai_thinking = False

            # Создание окна игры
            self.draw_window()

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    quit()

                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN:
                        command_move = input('Введите команду:')
                        self.get_valid_command(command_move)
                    elif event.key == pygame.K_a:
                        # Инструменты ИИ
                        self.ai_enabled = not self.ai_enabled
                        if self.ai_enabled and not self.ai:
                            self.ai = ChessAI()

                if event.type == pygame.MOUSEBUTTONUP and not self.ai_thinking:
                    # Работает, если ходит игрок или модель вырублена
                    if not self.ai_enabled or self.chess_board.curr_player == 'w':
                        self.get_user_click()

            self.clock.tick(60)

    def make_ai_move(self):
        if not self.ai:
            return

        # рабочие ходы
        self.all_poss_moves = self.get_all_poss_moves()

        rules = self.ai_rules_black if self.chess_board.curr_player == 'b' else self.ai_rules_white

        move = self.ai.choose_move(self.chess_board, self.all_poss_moves, rules=rules)
        if not move:
            return

        from_pos, to_pos = move
        piece = self.chess_board.get_piece_at(from_pos)
        if not piece:
            return

        # логика применения хода
        self.new_piece_selected(from_pos)

        if to_pos in self.curr_poss_moves:
            if piece.name == 'King' and to_pos in self.chess_board.get_castle_moves_for_curr_player():
                self.add_move(piece.position, to_pos)
                self.chess_board.castle_king(piece, to_pos)
            else:
                self.add_move(piece.position, to_pos)
                self.move_piece(piece, to_pos)

                if piece.name == 'Pawn' and (to_pos[1] == 0 or to_pos[1] == 7):
                    self.chess_board.board[to_pos[0]][to_pos[1]] = None
                    self.chess_board.board[to_pos[0]][to_pos[1]] = Queen(self.chess_board.curr_player, to_pos)

            self.deselect_piece()
            self.change_curr_player()
            self.all_poss_moves = self.get_all_poss_moves()
            self.check_checkmate()

    def draw_window(self):
        """Draws everything in the window"""
        self.game_display.fill(white)
        # Рисовка доски
        self.draw_board()
        
        # Отображение статуса ИИ
        font = pygame.font.Font(None, 36)
        ai_text = f"AI: {'ON' if self.ai_enabled else 'OFF'}"
        text_surface = font.render(ai_text, True, red)
        self.game_display.blit(text_surface, (0, 0))
        
        if self.ai_thinking:
            thinking_text = font.render("AI Thinking...", True, red)
            self.game_display.blit(thinking_text, (0, 50))
        
        pygame.display.update()

    def draw_board(self):
        # Отображение доски
        self.game_display.blit(self.board_image, (0, 0))

        # Отображение фигур
        for piece in self.chess_board.get_all_pieces():
            image_position = piece.position
            image_position = image_position[0] * 75, (7 - image_position[1]) * 75
            piece_image = pygame.image.load(piece.image)
            self.game_display.blit(piece_image, image_position)

        # Подсветка ходов
        if self.curr_selected_piece:
            box_x, box_y = self.convert_space_to_coordinates(self.curr_selected_piece.position)
            pygame.draw.rect(self.game_display, blue, Rect((box_x, box_y), (75, 75)), 5)
            
            for move in self.curr_poss_moves:
                box1_x, box1_y = self.convert_space_to_coordinates(move)
                pygame.draw.rect(self.game_display, red, Rect((box1_x, box1_y), (75, 75)), 5)

    def check_checkmate(self):
        """Проверка шаха и отображение"""
        checkmate = True
        for piece_pos in self.all_poss_moves:
            if len(self.all_poss_moves[piece_pos]) != 0:
                checkmate = False
                
        if checkmate:
            self.draw_window()
            self.message_display('Checkmate!', (300, 300))
            winner = 'White' if self.chess_board.curr_player == 'b' else 'Black'
            self.message_display(f'{winner} wins!', (300, 400))
            pygame.display.update()
            time.sleep(5)
            quit()

    def get_valid_command(self, command):
        square_piece_from = tuple(map(lambda x: int(x), command.split(',')[0].split())) # [3, 1]
        square_piece_to = tuple(map(lambda x: int(x), command.split(',')[1].split()))
        print(square_piece_from, square_piece_to)
        if self.is_piece_of_curr_player(square_piece_from):
            poss_moves = self.all_poss_moves[square_piece_from]
            self.new_piece_selected(square_piece_from)
            if square_piece_to in poss_moves:
                #### Проверка фигуры на короля ###
                if self.curr_selected_piece.name == 'King' and square_piece_to in self.chess_board.get_castle_moves_for_curr_player():
                    self.add_move(self.curr_selected_piece.position, square_piece_to)
                    self.chess_board.castle_king(self.curr_selected_piece, square_piece_to)
                else:
                    # Передвижение фигуры
                    self.add_move(self.curr_selected_piece.position, square_piece_to)
                    self.move_piece(self.curr_selected_piece, square_piece_to)

                    if self.curr_selected_piece.name == 'Pawn' and (square_piece_to[1] == 0 or square_piece_to[1] == 7):
                        self.chess_board.board[square_piece_to[0]][square_piece_to[1]] = None
                        self.chess_board.board[square_piece_to[0]][square_piece_to[1]] = Queen(self.chess_board.curr_player, square_piece_to)

                self.deselect_piece()
                self.change_curr_player()

                # Проверка на шах и обновление ходов
                self.all_poss_moves = self.get_all_poss_moves()
                checkmate = True
                for piece_pos in self.all_poss_moves:
                    if len(self.all_poss_moves[piece_pos]) != 0:
                        checkmate = False
                if checkmate:
                    self.draw_window()
                    self.message_display('Checkmate!', (300, 300))
                    winner = 'White' if self.chess_board.curr_player == 'b' else 'Black'
                    self.message_display('%s wins!' % winner, (300, 400))
                    pygame.display.update()
                    time.sleep(5)
                    quit()
        else:
            self.deselect_piece()

    def get_user_click(self):
        """Анализ позиции игрока"""
        x, y = pygame.mouse.get_pos()
        # Проверка клика на:
        # On bottom menu
        if y > 600:
            pass
        # On right side menu
        elif x > 600:
            pass
        # Если на доске
        else:
            # Конвертация координат
            selected_space = self.convert_coordinates_to_space(x, y)
            if not self.curr_selected_piece:

                # Выбор фигуры
                if self.is_piece_of_curr_player(selected_space):
                    self.new_piece_selected(selected_space)

            # Если фигура выбрана
            else:
                # Проверка на возможность ходить
                if selected_space == self.curr_selected_piece.position:
                    self.deselect_piece()

                elif selected_space in self.curr_poss_moves:
                    #### Проверка на короля ###
                    if self.curr_selected_piece.name == 'King' and selected_space in self.chess_board.get_castle_moves_for_curr_player():
                            self.add_move(self.curr_selected_piece.position, selected_space)
                            self.chess_board.castle_king(self.curr_selected_piece, selected_space)

                    else:
                        self.add_move(self.curr_selected_piece.position, selected_space)
                        self.move_piece(self.curr_selected_piece, selected_space)

                        if self.curr_selected_piece.name == 'Pawn' and (selected_space[1] == 0 or selected_space[1] == 7):
                            self.chess_board.board[selected_space[0]][selected_space[1]] = None
                            self.chess_board.board[selected_space[0]][selected_space[1]] = Queen(self.chess_board.curr_player, selected_space)

                    self.deselect_piece()
                    self.change_curr_player()

                    self.all_poss_moves = self.get_all_poss_moves()
                    checkmate = True
                    for piece_pos in self.all_poss_moves:
                        if len(self.all_poss_moves[piece_pos]) != 0:
                            checkmate = False
                    if checkmate:
                        self.draw_window()
                        self.message_display('Checkmate!', (300, 300))
                        winner = 'White' if self.chess_board.curr_player == 'b' else 'Black'
                        self.message_display('%s wins!' % winner, (300, 400))
                        pygame.display.update()
                        time.sleep(5)
                        quit()

                elif selected_space in [piece.position for piece in self.chess_board.get_curr_player_pieces()]:
                    self.new_piece_selected(selected_space)

                else:
                    self.deselect_piece()

    def convert_coordinates_to_space(self, x, y):
        return x // 75, 7 - y // 75


    def convert_space_to_coordinates(self, position):
        return position[0] * 75, (7 - position[1]) * 75

    def is_piece_of_curr_player(self, space):
        for piece in self.chess_board.get_curr_player_pieces():
            if space == piece.position:
                return True

    def get_all_poss_moves(self):
        moves = {}
        pieces = self.chess_board.get_curr_player_pieces()
        for piece in pieces:
            p_moves = self.chess_board.get_poss_moves_for(piece)
            moves[piece.position] = self.chess_board.is_curr_player_in_check(piece, p_moves)
        return moves

    def get_curr_poss_moves(self):
        """Возможные ходы"""
        return self.all_poss_moves[self.curr_selected_piece.position]

    def get_all_played_moves(self):
        return self.chess_board.played_moves

    def move_piece(self, piece, new_position):
        """Передвижение фигур, но не проверка на возможность"""
        piece_captured = self.chess_board.move_piece(piece, new_position)
        if piece_captured:
            self.piece_was_captured(piece_captured)

    def change_curr_player(self):
        """Игрок между белыми и чёрными (w and b)"""
        self.chess_board.curr_player = 'w' if self.chess_board.curr_player == 'b' else 'b'

    def new_piece_selected(self, new_space):
        """Обновление возможных ходов"""
        self.curr_selected_piece = self.chess_board.get_piece_at(new_space)
        self.curr_poss_moves = self.get_curr_poss_moves()

    def deselect_piece(self):
        """Отмена выбора фигуры"""
        self.curr_selected_piece = None
        self.curr_poss_moves = None

    def add_move(self, pos_1, pos_2):
        """Добавление ходов в лист ходов (Вырезано)"""
        name = self.chess_board.curr_player.upper() + ':     '
        move = name + self.convert_coordinate_to_space_name(pos_1) + ' -> ' + self.convert_coordinate_to_space_name(pos_2)
        self.chess_board.played_moves.append(move)

    def convert_coordinate_to_space_name(self, coordinate):
        """Конвертация ходов ((1,3) -> 'B3')"""
        conversions = {0 : 'A', 1: 'B', 2: 'C', 3: 'D', 4: 'E', 5: 'F', 6: 'G', 7: 'H'}
        return str(conversions[coordinate[0]]) + str(coordinate[1] + 1)

    def piece_was_captured(self, piece):
        """Обновление выбывших фигур (Вырезано)"""
        if piece.color == 'w':
            self.white_pieces_taken_images.append(piece.image)
        else:
            self.black_pieces_taken_images.append(piece.image)

    def message_display(self, text, point, fontsize=90):
        """отображение сообщения в окне"""
        large_text = pygame.font.Font('freesansbold.ttf', fontsize)
        text_surface = large_text.render(text, True, black)
        text_rect = text_surface.get_rect()
        text_rect.center = (point)
        self.game_display.blit(text_surface, text_rect)

if __name__ == '__main__':
    white = (232, 230, 202)
    blue = (34, 0, 255)
    red = (209, 9, 9)
    black = (0, 0, 0)

    Game(ai_enabled=True, engine_path="engines/stockfish/stockfish-windows-x86-64-avx2.exe") # путь к бинарнику движка