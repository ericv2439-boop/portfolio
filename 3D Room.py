import pygame
import math
import sys

# --- Initialize ---
pygame.init()
WIDTH, HEIGHT = 800, 600
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Pseudo 3D Room")

clock = pygame.time.Clock()
FPS = 60

# --- Player ---
player_x, player_y = 3.0, 3.0
player_angle = 0.0
player_speed = 0.05
rot_speed = 0.03

# --- Map ---
game_map = [
    [1,1,1,1,1,1,1,1],
    [1,0,0,0,0,0,0,1],
    [1,0,0,0,0,0,0,1],
    [1,0,0,0,0,0,0,1],
    [1,0,0,0,0,0,0,1],
    [1,0,0,0,0,0,0,1],
    [1,1,1,1,1,1,1,1],
]

MAP_WIDTH = len(game_map[0])
MAP_HEIGHT = len(game_map)
TILE_SIZE = 64

# --- Colors ---
GRAY = (80,80,80)
FLOOR_COLOR = (120, 120, 120)
CEILING_COLOR = (180, 180, 180)

# --- Raycasting ---
FOV = math.pi / 3
NUM_RAYS = 120
MAX_DEPTH = 20
DELTA_ANGLE = FOV / NUM_RAYS
DIST = NUM_RAYS / (2 * math.tan(FOV / 2))
SCALE = WIDTH / NUM_RAYS

def ray_casting():
    start_angle = player_angle - FOV/2
    for ray in range(NUM_RAYS):
        angle = start_angle + ray * DELTA_ANGLE
        sin_a = math.sin(angle)
        cos_a = math.cos(angle)

        for depth in range(1, MAX_DEPTH * TILE_SIZE):
            x = player_x * TILE_SIZE + depth * cos_a
            y = player_y * TILE_SIZE + depth * sin_a

            map_x = int(x // TILE_SIZE)
            map_y = int(y // TILE_SIZE)

            if map_x < 0 or map_x >= MAP_WIDTH or map_y < 0 or map_y >= MAP_HEIGHT:
                break

            if game_map[map_y][map_x] == 1:
                depth *= math.cos(player_angle - angle)  # remove fish-eye
                wall_height = min(int((TILE_SIZE * 300) / (depth + 0.0001)), HEIGHT)
                # Draw solid gray wall
                pygame.draw.rect(screen, GRAY, (ray*SCALE, HEIGHT//2 - wall_height//2, SCALE+1, wall_height))
                break

# --- Main loop ---
running = True
while running:
    screen.fill(CEILING_COLOR)
    pygame.draw.rect(screen, FLOOR_COLOR, (0, HEIGHT//2, WIDTH, HEIGHT//2))

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

    keys = pygame.key.get_pressed()
    if keys[pygame.K_w]:
        player_x += player_speed * math.cos(player_angle)
        player_y += player_speed * math.sin(player_angle)
    if keys[pygame.K_s]:
        player_x -= player_speed * math.cos(player_angle)
        player_y -= player_speed * math.sin(player_angle)
    if keys[pygame.K_a]:
        player_angle -= rot_speed
    if keys[pygame.K_d]:
        player_angle += rot_speed

    # Collision detection
    if game_map[int(player_y)][int(player_x)] == 1:
        player_x -= player_speed * math.cos(player_angle)
        player_y -= player_speed * math.sin(player_angle)

    ray_casting()

    pygame.display.flip()
    clock.tick(FPS)

pygame.quit()
sys.exit()
