import pygame
import math
import random

pygame.init()

WIDTH, HEIGHT = 900, 700
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Cube Sandbox v2")

clock = pygame.time.Clock()

# ---------- cube geometry ----------

vertices = [
(-1,-1,-1),(1,-1,-1),(1,1,-1),(-1,1,-1),
(-1,-1,1),(1,-1,1),(1,1,1),(-1,1,1)
]

edges = [
(0,1),(1,2),(2,3),(3,0),
(4,5),(5,6),(6,7),(7,4),
(0,4),(1,5),(2,6),(3,7)
]

# ---------- state ----------

angle_x = 0
angle_y = 0

angular_vx = 0.01
angular_vy = 0.02

slow_mode = False
rainbow_mode = False
trail_mode = False
orbit_mode = False

cube_color = (120,200,255)

# ---------- orbit ----------

orbit_angle = 0
orbit_speed = 0
orbit_radius = 3
orbit_cubes = 12

orbit_trails = [[] for _ in range(orbit_cubes)]
max_trail = 30

# ---------- UI ----------

slow_button = pygame.Rect(10,10,90,35)
color_button = pygame.Rect(110,10,90,35)
trail_button = pygame.Rect(210,10,90,35)
rainbow_button = pygame.Rect(310,10,50,35)

orbit_button = pygame.Rect(WIDTH-35, HEIGHT-35, 22, 22)
trail_toggle = pygame.Rect(10, HEIGHT-35, 22, 22)

font = pygame.font.SysFont(None,24)

# ---------- rotation ----------

def rotate(v, ax, ay):

    x,y,z = v

    cosx = math.cos(ax)
    sinx = math.sin(ax)

    cosy = math.cos(ay)
    siny = math.sin(ay)

    y,z = y*cosx - z*sinx, y*sinx + z*cosx
    x,z = x*cosy + z*siny, -x*siny + z*cosy

    return x,y,z


# ---------- projection ----------

def project(x,y,z):

    if z < -3.5:
        return None

    factor = 200/(z+4)

    sx = x*factor + WIDTH/2
    sy = y*factor + HEIGHT/2

    return (sx,sy)


# ---------- main loop ----------

running = True

while running:

    for event in pygame.event.get():

        if event.type == pygame.QUIT:
            running = False

        if event.type == pygame.KEYDOWN:

            if event.key == pygame.K_LEFT:
                angular_vy -= 0.02

            if event.key == pygame.K_RIGHT:
                angular_vy += 0.02

            if event.key == pygame.K_UP:
                angular_vx -= 0.02

            if event.key == pygame.K_DOWN:
                angular_vx += 0.02

        if event.type == pygame.MOUSEBUTTONDOWN:

            if slow_button.collidepoint(event.pos):
                slow_mode = not slow_mode

            if color_button.collidepoint(event.pos):
                cube_color = (
                    random.randint(80,255),
                    random.randint(80,255),
                    random.randint(80,255)
                )

            if trail_button.collidepoint(event.pos):
                trail_mode = not trail_mode

            if rainbow_button.collidepoint(event.pos):
                rainbow_mode = not rainbow_mode

            if orbit_button.collidepoint(event.pos):
                orbit_mode = not orbit_mode

            if trail_toggle.collidepoint(event.pos):
                trail_mode = not trail_mode

    # ---------- physics ----------

    if slow_mode:
        angular_vx *= 0.96
        angular_vy *= 0.96

    angle_x += angular_vx
    angle_y += angular_vy

    central_spin = angular_vx + angular_vy

    if orbit_mode:
        orbit_speed += (-central_spin)*0.02
        orbit_speed *= 0.98

    orbit_angle += orbit_speed

    # ---------- background ----------

    screen.fill((10,10,18))

    # ---------- central cube ----------

    rotated = [rotate(v,angle_x,angle_y) for v in vertices]

    points = []

    for x,y,z in rotated:

        p = project(x,y,z)

        if p:
            points.append(p)
        else:
            points.append(None)

    for edge in edges:

        a = points[edge[0]]
        b = points[edge[1]]

        if a and b:

            if rainbow_mode:
                color = (
                    random.randint(120,255),
                    random.randint(120,255),
                    random.randint(120,255)
                )
            else:
                color = cube_color

            pygame.draw.line(screen,color,a,b,2)

    # ---------- orbit cubes ----------

    if orbit_mode:

        for i in range(orbit_cubes):

            ang = orbit_angle + i*(2*math.pi/orbit_cubes)

            ox = math.cos(ang)*orbit_radius
            oz = math.sin(ang)*orbit_radius
            oy = math.sin(ang*2 + orbit_angle)*0.5

            orbit_vertices = [(vx+ox,vy+oy,vz+oz) for vx,vy,vz in vertices]

            rotated_orbit = [rotate(v,angle_x,angle_y) for v in orbit_vertices]

            orbit_points = []

            for x,y,z in rotated_orbit:

                p = project(x,y,z)

                if p:
                    orbit_points.append(p)
                else:
                    orbit_points.append(None)

            valid = [p for p in orbit_points if p]

            if valid:

                cx = sum(p[0] for p in valid)/len(valid)
                cy = sum(p[1] for p in valid)/len(valid)

                if 0 < cx < WIDTH and 0 < cy < HEIGHT:
                    orbit_trails[i].append((cx,cy))
                else:
                    orbit_trails[i].clear()

                if len(orbit_trails[i]) > max_trail:
                    orbit_trails[i].pop(0)

                if trail_mode:

                    trail = orbit_trails[i]

                    for t in range(1,len(trail)):

                        fade = t/len(trail)

                        color = (
                            int(180*fade),
                            int(100*fade),
                            int(200*fade)
                        )

                        pygame.draw.line(screen,color,trail[t-1],trail[t],1)

            hue = (i/orbit_cubes + orbit_angle*0.1)%1

            color = (
                int(200+55*math.sin(hue*6.28)),
                int(150+105*math.sin(hue*6.28+2)),
                int(200+55*math.sin(hue*6.28+4))
            )

            for edge in edges:

                a = orbit_points[edge[0]]
                b = orbit_points[edge[1]]

                if a and b:
                    pygame.draw.line(screen,color,a,b,1)

    # ---------- UI ----------

    slow_color = (60,180,90) if slow_mode else (60,60,60)
    pygame.draw.rect(screen,slow_color,slow_button,border_radius=6)
    pygame.draw.rect(screen,(60,60,60),color_button,border_radius=6)
    pygame.draw.rect(screen,(60,60,60),trail_button,border_radius=6)
    pygame.draw.rect(screen,(60,60,60),rainbow_button,border_radius=6)

    screen.blit(font.render("SLOW",True,(220,220,220)),(28,18))
    screen.blit(font.render("COLOR",True,(220,220,220)),(128,18))
    screen.blit(font.render("TRAIL",True,(220,220,220)),(232,18))
    screen.blit(font.render("?",True,(220,220,220)),(330,18))

    pygame.draw.rect(screen,(80,80,80),orbit_button,border_radius=6)
    pygame.draw.rect(screen,(80,80,80),trail_toggle,border_radius=6)

    pygame.display.flip()

    clock.tick(60)

pygame.quit()
