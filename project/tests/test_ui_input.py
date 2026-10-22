"""SDL event fixtures: no physical input devices or global mappings are changed."""
import unittest

try:
    import sdl2
    from psp_shell.ui.input import InputMapper
except ImportError:
    sdl2 = None

from psp_shell.ui.model import Preferences


@unittest.skipIf(sdl2 is None, "Install the optional host PySDL2 dependency")
class InputTests(unittest.TestCase):
    def setUp(self):
        self.mapper = InputMapper(manage_controllers=False, sample_initial_state=False)

    def tearDown(self):
        self.mapper.close()

    @staticmethod
    def key(symbol, down=True, repeat=False):
        event = sdl2.SDL_Event()
        event.type = sdl2.SDL_KEYDOWN if down else sdl2.SDL_KEYUP
        event.key.keysym.sym = symbol
        event.key.repeat = repeat
        return event

    @staticmethod
    def button(button, down=True):
        event = sdl2.SDL_Event()
        event.type = sdl2.SDL_CONTROLLERBUTTONDOWN if down else sdl2.SDL_CONTROLLERBUTTONUP
        event.cbutton.which = 17
        event.cbutton.button = button
        return event

    @staticmethod
    def axis(value):
        event = sdl2.SDL_Event()
        event.type = sdl2.SDL_CONTROLLERAXISMOTION
        event.caxis.which = 17
        event.caxis.axis = sdl2.SDL_CONTROLLER_AXIS_LEFTX
        event.caxis.value = value
        return event

    def test_south_and_east_confirm_are_ui_only(self):
        action = self.mapper.process(self.button(sdl2.SDL_CONTROLLER_BUTTON_A), Preferences(confirm="south"))
        self.assertEqual(action[0].action, "confirm")
        self.mapper.process(self.button(sdl2.SDL_CONTROLLER_BUTTON_A, False))
        action = self.mapper.process(self.button(sdl2.SDL_CONTROLLER_BUTTON_A), Preferences(confirm="east"))
        self.assertEqual(action[0].action, "back")

    def test_transition_gate_requires_all_held_buttons_released(self):
        self.assertEqual(self.mapper.process(self.key(sdl2.SDLK_RETURN))[0].action, "confirm")
        self.mapper.block_held()
        self.assertEqual(self.mapper.process(self.key(sdl2.SDLK_DOWN)), [])
        self.mapper.process(self.key(sdl2.SDLK_RETURN, False))
        self.assertEqual(self.mapper.tick(100), [])
        self.mapper.process(self.key(sdl2.SDLK_DOWN, False))
        self.assertEqual(self.mapper.process(self.key(sdl2.SDLK_RETURN))[0].action, "confirm")

    def test_confirm_repeat_never_reactivates_and_nav_has_no_backlog(self):
        self.mapper.process(self.key(sdl2.SDLK_RETURN), now=0)
        self.assertEqual(self.mapper.process(self.key(sdl2.SDLK_RETURN, repeat=True), now=1), [])
        self.assertEqual(self.mapper.tick(100), [])
        self.mapper.process(self.key(sdl2.SDLK_RETURN, False), now=100)
        self.mapper.process(self.key(sdl2.SDLK_DOWN), now=100)
        self.assertEqual(self.mapper.tick(100.2), [])
        self.assertEqual([a.action for a in self.mapper.tick(110)], ["down"])
        self.assertEqual(self.mapper.tick(110), [])

    def test_axis_hysteresis_rejects_drift_and_keeps_one_direction(self):
        self.assertEqual(self.mapper.process(self.axis(14000), now=0), [])
        self.assertEqual(self.mapper.process(self.axis(20000), now=0)[0].action, "right")
        self.assertEqual(self.mapper.process(self.axis(15000), now=0.1), [])
        self.mapper.process(self.axis(0), now=0.2)
        self.assertEqual(self.mapper.process(self.axis(-20000), now=0.3)[0].action, "left")

    def test_focus_loss_cannot_turn_old_repeat_into_confirmation(self):
        self.mapper.process(self.key(sdl2.SDLK_RETURN))
        event = sdl2.SDL_Event()
        event.type = sdl2.SDL_WINDOWEVENT
        event.window.event = sdl2.SDL_WINDOWEVENT_FOCUS_LOST
        self.mapper.process(event)
        self.assertEqual(self.mapper.process(self.key(sdl2.SDLK_RETURN, repeat=True)), [])

    def test_text_mode_reserves_enter_and_does_not_trigger_search_shortcut(self):
        self.assertEqual(self.mapper.process(self.key(sdl2.SDLK_x), text_mode=True), [])
        self.assertEqual(self.mapper.process(self.key(sdl2.SDLK_RETURN), text_mode=True)[0].action, "submit_text")
        event = sdl2.SDL_Event()
        event.type = sdl2.SDL_TEXTINPUT
        event.text.text = "é".encode("utf-8")
        self.assertEqual(self.mapper.process(event, text_mode=True)[0].text, "é")

    def test_removed_controller_cannot_leave_a_held_navigation_repeat(self):
        self.mapper.process(self.button(sdl2.SDL_CONTROLLER_BUTTON_DPAD_DOWN), now=0)
        self.mapper.block_held()
        event = sdl2.SDL_Event()
        event.type = sdl2.SDL_CONTROLLERDEVICEREMOVED
        event.cdevice.which = 17
        self.mapper.process(event, now=1)
        self.assertEqual(self.mapper.tick(20), [])
        self.assertEqual(self.mapper.process(self.key(sdl2.SDLK_RETURN), now=21)[0].action, "confirm")


if __name__ == "__main__":
    unittest.main()
