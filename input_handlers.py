from typing import Optional

import tcod.event

from actions import Action, EscapeAction, MovementAction

class EventHandler(tcod.event.EventDispatch[Action]):
    def ev_quit(self, event:tcod.event.Quit) -> Optional[Action]:
        raise SystemExit()
    
    def ev_keyDown(self, event:tcod.event.KeyDown) -> Optional[Action]:
        action: Optional[Action] = None

        key = event.sym

        if key == event.tcod.K_UP:
            action = MovementAction(dx=0, dy=-1)
        elif key == event.tcod.K_DOWN:
            action = MovementAction(dx=0, dy=1)
        elif key == event.tcod.K_LEFT:
            action = MovementAction(dx=1, dy=0)
        elif key == event.tcod.K_RIGHT:
            action = MovementAction(dx=-1, dy=0)

        elif key == event.tcod.K_ESCAPE:
            action = EscapeAction

        # no valid key was pressed
        return action

