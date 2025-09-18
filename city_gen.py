from typing import List, Tuple
import random

from game_map import GameMap
from rectangular_structure import RectangularStructure
from rectangular_road import RectangularRoad
from rectangular_room import RectangularRoom
import tile_types
import entity_factory
from dialog_data.default_text import WELCOME_TEXT
from utility import slices_to_xys

CITY_DEFAULTS = {
    "MAP_WIDTH": 50,
    "MAP_HEIGHT": 50,
    "MAX_LEVELS": 2,
    "MIN_BLOCK_SIZE": 10,
    "TREE_BORDER_WIDTH": 3,
    "ROAD_WIDTH": 3,
    "REQUIRED_STRUCTURES": [
        "MDU",
        "Library",
    ],
    "FILLER_STRUCTURES": [
        # "Park",
        # "Bathroom",
        # "Lobby",
        "Office",
        # "Conference Room",
    ],
}


def generate_city(
    engine,
    city_details=CITY_DEFAULTS,
):
    # Init
    player = engine.player
    map_width = city_details["MAP_WIDTH"]
    map_height = city_details["MAP_HEIGHT"]
    levels = city_details["MAX_LEVELS"]
    city = GameMap(engine, map_width, map_height, levels, entities=[player])

    generate_ground_and_sky(city, levels)

    # Tree Border
    border_width = city_details["TREE_BORDER_WIDTH"]
    generate_tree_border(city=city, border_width=border_width)

    # Section off city into roads and blocks
    blocks, road_spots = divide_cityspace(
        city, border_width, city_details["MIN_BLOCK_SIZE"]
    )

    # Draw roads, including exit
    road_spots = generate_city_out_road(city, road_spots, border_width)
    roads = generate_roads(city, road_spots)

    # Draw buildings
    structures = blocks_to_structures(blocks)
    structures_and_types = generate_structure_types(structures, city_details)

    for structure, structure_type in structures_and_types.items():
        generate_structure_details(city, structure, structure_type, city_details)

    # Generate Actors and Items
    generate_actors(city, player, structures, roads)

    # Generate Player
    generate_player(city, player)

    sign = place_entity(city, 1, (4, 2), entity_factory.sign, True)
    sign.information.clear()
    sign.information.add_page(WELCOME_TEXT)
    return city


def generate_ground_and_sky(city, levels):
    rows = city.height
    cols = city.width
    map_struct = RectangularStructure(0, 0, cols - 1, rows - 1)
    place_tiles(city, 0, map_struct.area, [tile_types.underground])
    if levels >= 2:
        for level in range(2, levels):
            place_tiles(city, level, map_struct.area, [tile_types.sky])


# CREATE GRID
def split_rectangle(rect: RectangularStructure, min_size=3, split_chance=0.6):
    """
    Split a rectangle into rooms of various sizes.
    Returns a list of RectangularStructure rooms.
    """
    rooms = []

    def _split(r: RectangularStructure):
        # Stop if too small
        if r.width <= min_size and r.height <= min_size:
            rooms.append(r)
            return

        # Randomly decide to split vertically or horizontally
        if random.random() < split_chance:
            # Vertical split (two side-by-side rooms)
            if r.width > min_size * 2 and (
                random.choice([True, False]) or r.height <= min_size * 2
            ):
                split_at = random.randint(min_size, r.width - min_size)
                left = RectangularStructure(r.x, r.y, split_at, r.height)
                right = RectangularStructure(
                    r.x + split_at, r.y, r.width - split_at, r.height
                )
                _split(left)
                _split(right)
                return

            # Horizontal split (two stacked rooms)
            if r.height > min_size * 2:
                split_at = random.randint(min_size, r.height - min_size)
                top = RectangularStructure(r.x, r.y, r.width, split_at)
                bottom = RectangularStructure(
                    r.x, r.y + split_at, r.width, r.height - split_at
                )
                _split(top)
                _split(bottom)
                return

        # No split — keep as is
        rooms.append(r)

    _split(rect)
    return rooms


def split_and_place_doors(rect: RectangularRoom, min_size=9):
    """Split the rectangle into rooms and place doors during each split."""
    rooms = []
    doors = []

    def _split(r: RectangularRoom):
        # Stop if too small
        if r.width <= min_size and r.height <= min_size:
            rooms.append(r)
            return

        # Decide split direction
        if r.width > r.height and r.width >= min_size * 2:
            # Vertical split
            split_at = random.randint(min_size, r.width - min_size)
            left = RectangularRoom(r.x, r.y, split_at, r.height)
            right = RectangularRoom(r.x + split_at, r.y, r.width - split_at, r.height)

            # Place door in the shared wall
            door_y = random.randint(r.y + 1, r.y + r.height - 2)
            door_x = r.x + split_at
            doors.append((door_x, door_y))
            left.add_door(door_x, door_y)
            right.add_door(door_x, door_y)

            _split(left)
            _split(right)

        elif r.height >= min_size * 2:
            # Horizontal split
            split_at = random.randint(min_size, r.height - min_size)
            top = RectangularRoom(r.x, r.y, r.width, split_at)
            bottom = RectangularRoom(r.x, r.y + split_at, r.width, r.height - split_at)

            # Place door in the shared wall
            door_x = random.randint(r.x + 1, r.x + r.width - 2)
            door_y = r.y + split_at
            doors.append((door_x, door_y))
            top.add_door(door_x, door_y)
            bottom.add_door(door_x, door_y)

            _split(top)
            _split(bottom)

        else:
            # No further split
            rooms.append(r)

    _split(rect)
    return rooms, doors


# GENERATE BORDER
def generate_tree_border(city, border_width):
    rows = city.height
    cols = city.width
    tree_level = 1
    for t in range(border_width):
        # Top and bottom row border
        for x in range(cols):
            place_tile(city, tree_level, (x, t), tile_types.TREE_TILES)
            place_tile(city, tree_level, (x, rows - 1 - t), tile_types.TREE_TILES)

        # Left and right column border
        for y in range(rows - t):
            place_tile(city, tree_level, (t, y), tile_types.TREE_TILES)
            place_tile(city, tree_level, (cols - 1 - t, y), tile_types.TREE_TILES)


def divide_cityspace(city, border_width, min_block_size):
    x = border_width
    y = border_width
    width = city.width - (2 * border_width)
    height = city.height - (2 * border_width)

    roads = []
    blocks = []

    queue = [RectangularStructure(x, y, width, height)]

    while queue:
        block = queue.pop(0)
        w, h = block.w, block.h

        # Check if we can split further
        if (
            w < min_block_size * 2 + CITY_DEFAULTS["ROAD_WIDTH"]
            and h < min_block_size * 2 + CITY_DEFAULTS["ROAD_WIDTH"]
        ):
            blocks.append(RectangularStructure(block.x + 1, block.y + 1, w - 3, h - 3))
            continue

        # Decide split direction
        split_horizontally = random.choice([True, False])
        if w < min_block_size * 2 + CITY_DEFAULTS["ROAD_WIDTH"]:
            split_horizontally = True
        elif h < min_block_size * 2 + CITY_DEFAULTS["ROAD_WIDTH"]:
            split_horizontally = False

        if split_horizontally:
            # Horizontal split
            split_line = random.randint(
                min_block_size, h - min_block_size - CITY_DEFAULTS["ROAD_WIDTH"]
            )
            roads.append(
                RectangularStructure(
                    block.x, block.y + split_line, w, CITY_DEFAULTS["ROAD_WIDTH"]
                )
            )

            # Top block
            queue.append(RectangularStructure(block.x, block.y, w, split_line))
            # Bottom block
            queue.append(
                RectangularStructure(
                    block.x,
                    block.y + split_line + CITY_DEFAULTS["ROAD_WIDTH"],
                    w,
                    h - split_line - CITY_DEFAULTS["ROAD_WIDTH"],
                )
            )
        else:
            # Vertical split
            split_line = random.randint(
                min_block_size, w - min_block_size - CITY_DEFAULTS["ROAD_WIDTH"]
            )
            roads.append(
                RectangularStructure(
                    block.x + split_line, block.y, CITY_DEFAULTS["ROAD_WIDTH"], h
                )
            )

            # Left block
            queue.append(RectangularStructure(block.x, block.y, split_line, h))
            # Right block
            queue.append(
                RectangularStructure(
                    block.x + split_line + CITY_DEFAULTS["ROAD_WIDTH"],
                    block.y,
                    w - split_line - CITY_DEFAULTS["ROAD_WIDTH"],
                    h,
                )
            )

    # Remaining blocks go to final list
    blocks.extend(
        RectangularStructure(block.x + 1, block.y + 1, block.w - 3, block.h - 3)
        for block in queue
    )
    return [b.as_tuple for b in blocks], [r.as_tuple for r in roads]


# ROADS
def generate_roads(city, road_dimensions):
    # Determine road sizes and number
    roads = []
    level = 1

    for x, y, w, h in road_dimensions:
        is_vertical = w < h
        road = RectangularRoad(x, y, w, h, is_vertical)
        divider_tile = (
            tile_types.road_divider_vert
            if is_vertical
            else tile_types.road_divider_horiz
        )

        place_tiles(city, level, road.center_line, [divider_tile])
        place_tiles(city, level, road.lanes, [tile_types.road])

        for other_road in roads:
            if road.abuts(other_road):
                for idx, spot in enumerate(road.abuts(other_road)):
                    if idx <= 2:
                        place_tile(city, level, spot, [tile_types.road])
                        # city.tiles[spot] = tile_types.chair_horiz
        roads.append(road)
    return roads


def generate_city_out_road(city, roads, border_width):
    """Extends one road at random so the player can exit the map"""
    w = city.width - (2 * border_width)
    h = city.height - (2 * border_width)

    random.shuffle(roads)
    for road in roads:
        if road[0] == border_width:
            road[0] = 0
            road[2] += border_width
            city.exit_locations = [(0, road[1]), (0, road[1] + 1), (0, road[1] + 2)]
            return roads
        elif road[1] == border_width:
            road[1] = 0
            road[3] += border_width
            city.exit_locations = [(road[0], 0), (road[0] + 1, 0), (road[0] + 2, 0)]
            return roads
        elif road[0] + road[2] + border_width == w:
            road[2] += border_width
            city.exit_locations = [
                (road[0] + road[2], road[1]),
                (road[0] + road[2], road[1] + 1),
                (road[0] + road[2], road[1] + 2),
            ]

            return roads
        elif road[1] + road[3] + border_width == h:
            road[3] += border_width
            city.exit_locations = [
                (road[0], road[1] + road[3]),
                (road[0] + 1, road[1] + road[3]),
                (road[0] + 2, road[1] + road[3]),
            ]

            return roads


def rect_touch_or_overlap(rects: List[Tuple[int, int, int, int]]):
    """Return (x, y, w, h) intersections or touching edges between rects."""
    results = []
    for i, (x1, y1, w1, h1) in enumerate(rects):
        for x2, y2, w2, h2 in rects[i + 1 :]:
            ix, iy = max(x1, x2), max(y1, y2)
            iw, ih = min(x1 + w1, x2 + w2) - ix, min(y1 + h1, y2 + h2) - iy
            if iw >= 0 and ih >= 0:  # allow touching (== 0) or overlapping (> 0)
                results.append((ix, iy, iw, ih))
    return results


def generate_structure_details(city, structure, structure_type, city_details):
    # TODO add more structures
    # TODO add structure division
    # TODO add new super structure type

    if structure_type in ["Park"]:
        num_trees = 6
        generate_park(city, structure, num_trees)
    else:
        generate_building(
            city,
            structure,
            structure_type,
            0,
            city_details["MAX_LEVELS"],
        )


def generate_building(
    city,
    structure,
    structure_type,
    bottom_floor=0,
    top_floor=CITY_DEFAULTS["MAX_LEVELS"],
):
    # TODO rethink stairwells, and this floor by floor generation method
    for floor in range(bottom_floor, top_floor):
        generate_flooring(city, floor, structure, tile_types.floor)
        generate_walls(city, floor, structure)

        rooms, doors = split_and_place_doors(structure, min_size=4)

        for room in rooms:
            generate_walls(city, floor, room)
            if structure_type == "Office":
                generate_office(city, 1, room)
                generate_stairwell(city, room)

            elif structure_type == "Conference Room":
                generate_conference_room(city, floor, room)

            elif structure_type == "Bathroom":
                generate_half_bathroom(city, floor, room)
                # generate_bathroom(city, floor, structure)

            elif structure_type == "Library":
                generate_library(city, floor, room)

            elif structure_type == "Lobby":
                generate_stairwell(city, room, horiz_spot=False)

            elif structure_type == "Single Floor Stairwell":
                generate_stairwell(city, room, 1, 2)
            elif structure_type == "Double Floor Stairwell":
                generate_stairwell(city, room, 1, 2)
            elif structure_type == "Full Stairwell":
                generate_stairwell(city, room)
            elif structure_type == "Cellar Door Stairwell":
                generate_stairwell(city, room, 0, 1)

        place_tiles(city, floor, doors, [tile_types.door], True)

        if floor > 0:
            generate_windows(city, floor, structure)
        if floor == 1:
            generate_doors(city, floor, structure)

    # stairwell = random.choice(structure.quadrant_centers)
    # generate_stairwell(city, structure, bottom_floor, top_floor, center_spot=stairwell)


def generate_stairwell(
    city,
    structure,
    bottom_floor=0,
    top_floor=CITY_DEFAULTS["MAX_LEVELS"],
    center_spot=None,
    horiz_spot=True,
):
    # ! FIX spot placement not really working
    x, y = center_spot or structure.center
    x_add, y_add = (1, 0) if horiz_spot else (0, 1)
    for floor in range(bottom_floor, top_floor):

        if floor % 2 == 0:
            down_spot = (x - x_add, y - y_add)
            up_spot = (x + x_add, y + y_add)
        else:
            down_spot = (x + x_add, y + y_add)
            up_spot = (x - x_add, y - y_add)

        if floor == bottom_floor:
            place_tile(city, floor, up_spot, [tile_types.up_stairs], True)
            city.stair_locations["UP"].append((floor, up_spot))
        elif floor == top_floor - 1:
            place_tile(city, floor, down_spot, [tile_types.down_stairs], True)
            city.stair_locations["DOWN"].append((floor, down_spot))
        else:
            place_tile(city, floor, up_spot, [tile_types.up_stairs], True)
            place_tile(city, floor, down_spot, [tile_types.down_stairs], True)
            city.stair_locations["UP"].append((floor, up_spot))
            city.stair_locations["DOWN"].append((floor, down_spot))


def blocks_to_structures(block_dimensions):
    structures = []
    structures.extend(RectangularRoom(x, y, w, h) for x, y, w, h in block_dimensions)
    return structures


def generate_structure_types(structures, details):
    required_types = details["REQUIRED_STRUCTURES"]
    filler_types = details["FILLER_STRUCTURES"]

    random.shuffle(structures)  # shuffle to randomize assignment

    structures_and_types = dict(zip(structures, required_types))
    # Step 2: Assign random types to remaining structures
    remaining_structures = structures[len(required_types) :]
    for structure in remaining_structures:
        structures_and_types[structure] = random.choice(filler_types)

    return structures_and_types


def generate_office(city, level, structure):
    size = len(slices_to_xys(*structure.inner))
    bookshelf_spots = random.choices(structure.along_inside_walls, k=max(1, size // 3))
    x, y = structure.center
    place_tiles(city, level, bookshelf_spots, tile_types.BOOKCASE_TILES, False)
    # place_tiles(city, level, [(x, y)], [tile_types.table], True)
    place_tiles(city, level, [(x, y - 1)], [tile_types.chair_horiz], True)

    if computer_desk := place_entity(
        city, level, (x, y), entity_factory.computer, False
    ):
        computer_desk.information.add_page("Hello! I should be on page 3!")


def generate_library(city, level, structure):
    inner = slices_to_xys(*structure.inner)
    ys = [y for x, y in inner]
    min_y, max_y = min(ys), max(ys)
    bookshelf_spots = [
        s for s in inner if s[0] % 2 == 0 and s[1] != min_y and s[1] != max_y
    ]
    place_tiles(city, level, bookshelf_spots, tile_types.BOOKCASE_TILES, False)


def generate_conference_room(city, level, structure):
    size = len(slices_to_xys(*structure.inner))
    room = structure
    if structure.width >= 9 and structure.height >= 9:
        room = RectangularRoom(
            structure.x + 2,
            structure.y + 2,
            structure.width - 4,
            structure.height - 4,
        )
        bookshelf_spots = random.choices(
            structure.along_inside_walls, k=max(1, size // 3)
        )
        place_tiles(city, level, bookshelf_spots, tile_types.BOOKCASE_TILES, False)
    elif structure.width >= 7 and structure.height >= 7:
        room = RectangularRoom(
            structure.x + 1,
            structure.y + 1,
            structure.width - 2,
            structure.height - 2,
        )
    xs = [x for x, y in room.along_inside_walls]
    ys = [y for x, y in room.along_inside_walls]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)

    corners = {(min_x, min_y), (min_x, max_y), (max_x, min_y), (max_x, max_y)}

    along_wo_corners = [spot for spot in room.along_inside_walls if spot not in corners]
    place_tiles(city, level, along_wo_corners, [tile_types.chair_horiz])
    place_tiles(city, level, room.inner_away_from_walls, [tile_types.table])


def generate_walls(city, level, structure: RectangularStructure, wall_type=None):
    for spot in structure.edges_and_corners:
        if spot in structure.vertical_edges:
            city.tiles[level][spot] = tile_types.vertical_wall
            continue
        if spot in structure.horizontal_edges:
            city.tiles[level][spot] = tile_types.horizontal_wall
            continue

        if spot == structure.top_left_corner:
            if city.tiles[level][spot] in [
                tile_types.bottom_left_corner_wall,
                tile_types.right_t_wall,
            ]:
                city.tiles[level][spot] = tile_types.right_t_wall
            elif city.tiles[level][spot] in [
                tile_types.top_right_corner_wall,
                tile_types.down_t_wall,
            ]:
                city.tiles[level][spot] = tile_types.down_t_wall
            elif city.tiles[level][spot] in [
                tile_types.bottom_right_corner_wall,
                tile_types.cross_wall,
                tile_types.left_t_wall,
                tile_types.up_t_wall,
            ]:
                city.tiles[level][spot] = tile_types.cross_wall
            else:
                city.tiles[level][spot] = tile_types.top_left_corner_wall
            continue
        elif spot == structure.top_right_corner:
            if city.tiles[level][spot] in [
                tile_types.bottom_right_corner_wall,
                tile_types.left_t_wall,
            ]:
                city.tiles[level][spot] = tile_types.left_t_wall
            elif city.tiles[level][spot] in [
                tile_types.top_left_corner_wall,
                tile_types.down_t_wall,
            ]:
                city.tiles[level][spot] = tile_types.down_t_wall
            elif city.tiles[level][spot] in [
                tile_types.bottom_left_corner_wall,
                tile_types.cross_wall,
                tile_types.right_t_wall,
                tile_types.up_t_wall,
            ]:
                city.tiles[level][spot] = tile_types.cross_wall
            else:
                city.tiles[level][spot] = tile_types.top_right_corner_wall
        elif spot == structure.bottom_left_corner:
            if city.tiles[level][spot] in [
                tile_types.top_left_corner_wall,
                tile_types.right_t_wall,
            ]:
                city.tiles[level][spot] = tile_types.right_t_wall
            elif city.tiles[level][spot] in [
                tile_types.bottom_right_corner_wall,
                tile_types.up_t_wall,
            ]:
                city.tiles[level][spot] = tile_types.up_t_wall
            elif city.tiles[level][spot] in [
                tile_types.top_right_corner_wall,
                tile_types.cross_wall,
                tile_types.left_t_wall,
                tile_types.down_t_wall,
            ]:
                city.tiles[level][spot] = tile_types.cross_wall
            else:
                city.tiles[level][spot] = tile_types.bottom_left_corner_wall
        elif spot == structure.bottom_right_corner:
            if city.tiles[level][spot] in [
                tile_types.top_right_corner_wall,
                tile_types.left_t_wall,
            ]:
                city.tiles[level][spot] = tile_types.left_t_wall
            elif city.tiles[level][spot] in [
                tile_types.bottom_left_corner_wall,
                tile_types.up_t_wall,
            ]:
                city.tiles[level][spot] = tile_types.up_t_wall
            elif city.tiles[level][spot] in [
                tile_types.top_left_corner_wall,
                tile_types.cross_wall,
                tile_types.right_t_wall,
                tile_types.down_t_wall,
            ]:
                city.tiles[level][spot] = tile_types.cross_wall
            else:
                city.tiles[level][spot] = tile_types.bottom_right_corner_wall
        else:
            city.tiles[level][spot] = tile_types.wall


def generate_flooring(city, level, structure, floor_tile=tile_types.floor):
    place_tiles(city, level, structure.inner, [floor_tile])


def generate_windows(city, level, structure, number_of_windows=4):
    windows_each = max(0, number_of_windows // 2)

    if len(structure.horizontal_edges) > windows_each:
        h_window_spots = random.sample(structure.horizontal_edges, k=windows_each)
        for spot in h_window_spots:
            if city.tiles[level][spot] in tile_types.FLAT_WALL_TILES:
                city.tiles[level][spot] = tile_types.horizontal_window

    if len(structure.vertical_edges) > windows_each:
        v_windows = random.sample(structure.vertical_edges, k=windows_each)
        for spot in v_windows:
            if city.tiles[level][spot] in tile_types.FLAT_WALL_TILES:
                city.tiles[level][spot] = tile_types.vertical_window


def generate_doors(city, level, structure):
    while True:
        (x, y) = random.choice(structure.edges)
        if place_doors_and_reserve_floor(city, level, structure, x, y):
            structure.add_door(x, y)
            return


def place_doors_and_reserve_floor(city, level, structure, x, y):
    if city.tiles[level][(x, y)] == tile_types.vertical_wall:
        place_tile(city, level, (x, y), [tile_types.door], True)
        if structure.is_inside(x - 1, y):
            left_tile = [tile_types.reserved_floor]
            right_tile = [tile_types.reserved_cement]
        else:
            left_tile = [tile_types.reserved_cement]
            right_tile = [tile_types.reserved_floor]
        place_tile(city, level, (x - 1, y), left_tile, True)
        place_tile(city, level, (x + 1, y), right_tile, True)
        return True
    elif city.tiles[level][(x, y)] == tile_types.horizontal_wall:
        place_tile(city, level, (x, y), [tile_types.door], True)
        if structure.is_inside(x, y - 1):
            up_tile = [tile_types.reserved_floor]
            down_tile = [tile_types.reserved_cement]
        else:
            up_tile = [tile_types.reserved_cement]
            down_tile = [tile_types.reserved_floor]
        place_tile(city, level, (x, y - 1), up_tile, True)
        place_tile(city, level, (x, y + 1), down_tile, True)
        return True
    return False


def generate_living_room():
    pass


def generate_kitchen():
    pass


def generate_bathroom(city, level, structure):
    spots = structure.inside_wall_same_as_door
    place_tiles(city, level, spots, [tile_types.sink], False)
    # spot = random.choice(structure.along_inside_walls)
    # place_tile(city, level, spot, [tile_types.sink], False)


# kill this; replaced by very_small_bathroom
def generate_half_bathroom(city, level, structure):
    spots = random.choices(structure.inside_wall_opposite_door, k=2)
    place_tile(city, level, spots[0], [tile_types.sink], True)
    place_tile(city, level, spots[1], [tile_types.tree], True)
    spot = random.choice(structure.along_inside_walls)
    place_tile(city, level, spot, [tile_types.bookcase_empty], False)


# !!!!
# a kitchen wall in a studio apartment
def generate_kitchen_wall(city, level, structure):
    # minimum = wall(3), depth(3)
    # needs a wall, a row of appliances, and a row of walking space, so depth = 3 including wall
    spots = random.choice(structure.inside_wall_right_of_door, k=3)
    place_tile(city, level, spots[0], [tile_types.sink], True)
    place_tile(city, level, spots[1], [tile_types.appliance_stovetop], True)
    place_tile(city, level, spots2], [tile_types.appliance_refrigerator], True)


def generate_very_small_storage_1(city, level, structure):
    # minimum room size: 3x4
    # this is an empty storage space or closet
    # might be a "portal" to another space?
    spot = random.choice(structure.inside_wall_opposite_door)
    place_tile(city, level, spot, [tile_types.shelves.empty], True)


def generate_very_small_storage_2(city, level, structure):
    # minimum room size: 3x4
    # could also be used for very_small_storage_3 and 4 wth new tiles: clothing_bar, shelves_empty
    # new tiles needed: tile.types.clothing_bar, tile.types.brooms_buckets, tile.types.shelves_empty
    spot = random.choice(structure.inside_wall_opposite_door)
    place_tile(city, level, spot, [tile_types.brooms_buckets], True)


def generate_very_small_storage_5(city, level, structure):
    # minimum room size: 3x5
    # could use any two tiles from: [none], clothing_bar, shelves_empty, brooms_buckets, sink
    # check: inside_wall_right_of_door, inside_wall_left_of_door
    spot = random.choice(structure.inside_wall_right_of_door)
    place_tile(city, level, spot, [tile_types.shelves.empty], True)
    spot = random.choice(structure.inside_wall_left_of_door)
    place_tile(city, level, spot, [tile_types.brooms_buckets], True)


# this replaces half_bathroom
def generate_very_small_bathroom(city, level, structure):
     # minimum room size: 4x4
     # new tiles: tile.types.toilet
    spots = random.choices(structure.inside_wall_opposite_door, k=2)
    place_tile(city, level, spots[0], [tile_types.sink], True)
    place_tile(city, level, spots[1], [tile_types.toilet], True)


def generate_small_bathroom_1(city, level, structure):
    # minimum room size: 4x5
    # new tiles: tile.types.shower
    spots = random.choices(structure.inside_wall_opposite_door, k=2)
    place_tile(city, level, spots[0], [tile_types.toilet], True)
    place_tile(city, level, spots[1], [tile_types.shower], True)
    spot = random.choice(structure.inside_wall_right_of_door)
    place_tile(city, level, spot, [tile_types.sink], True)


def generate_very_small_bedroom_1(city, level, structure):
    # minimum room size: 4x6
    # new tiles: tile.types.bed; tile.types.dresser
    spot = random.choice(structure.inside_wall_opposite_door)
    place_tile(city, level, spot, [tile_types.bed], True)
    spot = random.choice(structure.inside_wall_right_of_door)
    place_tile(city, level, spot, [tile_types.dresser], True)


def generate_small_bathroom_5(city, level, structure):
    # minimum room size: 5x5
    # new: tile.types.bathtub
    spots = random.choices(structure.inside_wall_opposite_door, k=2)
    place_tile(city, level, spots[0], [tile_types.toilet], True)
    place_tile(city, level, spots[1], [tile_types.sink], True)
    spot = random.choice(structure.inside_wall_right_of_door)
    place_tile(city, level, spot, [tile_types.bathtub], True)


def generate_small_kitchen_1(city, level, structure):
    # minimum room siz 5x5
    spot = random.choice(structure.inside_wall_right_of_door)
    place_tile(city, level, spot, [tile_types.refrigerator], True)
    spot = random.choice(structure.inside_wall_left_of_door)
    place_tile(city, level, spot, [tile_types.stovetop], True)
    spot = random.choice(structure.inside_wall_opposite_door)
    place_tile(city, level, spot, [tile_types.sink], True)


def generate_small_office_1(city, level, structure):
    # minimum room size: 5x6
    #new: tile.types.desk; tile.types.chair
    # !!!!!
    # the placement of these objects could be improved or more realistic, if needed
    spots = random.choices(structure.inside_wall_opposite_door, k=2)
    place_tile(city, level, spots[0], [tile_types.shelves], True)
    place_tile(city, level, spots[1], [tile_types.desk], True)
    spots = random.choice(structure.inside_wall_right_of_door, k=2)
    place_tile(city, level, spot, [tile_types.chair], True)
    place_tile(city, level, spot, [tile_types.cabinet], True)


def generate_bathroom_1(city, level, structure):
    # minimum room size: 5x6
    spots = random.choices(structure.inside_wall_opposite_door, k=2)
    place_tile(city, level, spots[0], [tile_types.toilet], True)
    place_tile(city, level, spots[1], [tile_types.sink], True)
    spot = random.choice(structure.inside_wall_right_of_door, k=2)
    place_tile(city, level, spot, [tile_types.bathtub], True)
    place_tile(city, level, spot, [tile_types.shower], True)


def generate_small_bedroom_2(city, level, structure):
    # minimum room size: 5x6
    spots = random.choices(structure.inside_wall_opposite_door, k=2)
    place_tile(city, level, spots[0], [tile_types.twin_bed], True)
    place_tile(city, level, spot, [tile_types.dresser], True)
    spot = random.choice(structure.inside_wall_right_of_door)
    place_tile(city, level, spot, [tile_types.desk], True)
    # !!!!
    # spot = unreserved tile opposite desk
    place_tile(city, level, spot, [tile_types.chair], True)


def generate_retail():
    pass


def generate_park(city, structure, num_trees=5):
    level = 1
    place_tiles(city, level, structure.area, tile_types.GRASS_TILES)
    spots = random.choices(slices_to_xys(*structure.area), k=num_trees)
    place_tiles(city, level, spots, tile_types.TREE_TILES)


def generate_actors(city, player, structures, roads):
    generate_npcs(city, structures, roads)
    generate_items(city, structures)


def generate_player(city, player):
    # ! FIX messes with alignment
    # if city.exit_locations:
    #     spot = random.choice(city.exit_locations)
    #     player.place(*spot, city)

    player.place(x=3, y=3, level=1, gamemap=city)


def generate_npcs(city, structures, roads):
    # level = 1
    npcs_to_generate = 25
    while npcs_to_generate:
        random_room = random.choice(structures)
        random_level = 1
        x, y = random.choice(slices_to_xys(*(random_room.inner)))
        place_entity(city, random_level, (x, y), entity_factory.npc)

        npcs_to_generate -= 1


def generate_items(city, structures):
    # TODO improve around item generation
    # TODO fix level / item generation
    # level = 1
    items_to_place = len(structures)
    items_to_place = 50
    while items_to_place:
        random_room = random.choice(structures)
        level = 1
        x, y = random.choice(slices_to_xys(*(random_room.inner)))

        val = random.random()
        if val <= 0.2:
            place_entity(city, level, (x, y), entity_factory.lightning_scroll, False)
        elif val <= 0.5:
            place_entity(city, level, (x, y), entity_factory.confusion_scroll, False)
        elif val <= 0.7:
            place_entity(city, level, (x, y), entity_factory.health_potion, False)
        else:
            place_entity(city, level, (x, y), entity_factory.fireball_scroll, False)

        items_to_place -= 1


def place_entity(city, level, spot, entity, override=False):
    if city.tiles[level][spot] in tile_types.EMPTY_TILES or override:
        return entity.spawn(city, level, *spot)


def place_tile(city, level, spot, tile_list, override=True):
    # TODO improve to handle reseved tiles?
    tile = random.choice(tile_list)
    if city.tiles[level][spot] in tile_types.EMPTY_TILES or override:
        city.tiles[level][spot] = tile


def place_tiles(city, level, spots, tile_list, override=True):
    locations = []
    if isinstance(spots, (List, list)):
        locations = spots
    elif isinstance(spots, Tuple):
        if isinstance(spots[0], slice) and isinstance(spots[1], slice):
            locations = slices_to_xys(*spots)
        else:
            locations = [spots]
    else:
        print(f"error placing tile from: {type(spots)}:")
        print(spots)

    for spot in locations:
        place_tile(city, level, spot, tile_list, override)
