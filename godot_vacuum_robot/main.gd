extends Node3D
"""Classroom whiteboard demo. The imported robot asset remains unchanged."""

const ROBOT_SCENE: PackedScene = preload("res://Vacuum_Robot_Blockout.glb")
const BOARD_SIZE := Vector2(2.4, 1.8) # board-local X and Z, metres
const BOARD_CENTER := Vector3(0.0, 2.35, -1.45)
const BATTERY_SECONDS := 60.0
const DRIVE_SPEED := 0.32
const TURN_SPEED := 2.1
const DOCK_POSITION := Vector3(1.098, 0.015, 0.661)
const DOCK_HEADING := PI # charger is turned 180° toward the board interior
const POGO_TIP_FORWARD := 0.1041
const POGO_LATERAL_SPACING := 0.032
const UI_REFRESH_INTERVAL := 0.1

var board_root: Node3D
var robot: Node3D
var camera: Camera3D
var erased_words: Array[Label3D] = []
var returning_to_dock := false
var parking_phase := 0
var fallen := false
var charging := false
var battery_seconds := BATTERY_SECONDS
var fall_velocity := Vector3.ZERO
var status_label: Label
var battery_label: Label
var clean_label: Label
var battery_bar: ProgressBar
var clean_bar: ProgressBar
var dock_material: StandardMaterial3D
var dock_light: OmniLight3D
var elapsed := 0.0
var ui_refresh_elapsed := 0.0
var low_performance_mode := false
var key_light: DirectionalLight3D
var robot_shadow_casters: Array[GeometryInstance3D] = []

func _ready() -> void:
	_build_classroom()
	key_light = get_node_or_null("KeyLight") as DirectionalLight3D
	Engine.max_fps = 60
	_build_wall_board()
	_build_dock()
	robot = ROBOT_SCENE.instantiate() as Node3D
	robot.name = "Whiteboard Robot"
	robot.position = Vector3(0.0, 0.015, 0.08)
	board_root.add_child(robot)
	_optimize_robot_shadows()
	_build_camera()
	_build_hud()
	Input.mouse_mode = Input.MOUSE_MODE_VISIBLE

func _build_classroom() -> void:
	var floor := _box("Classroom Floor", Vector3(12.0, 0.16, 12.0), Vector3(0, -0.10, 1.0), Color(0.20, 0.24, 0.28), 0.0, 0.84)
	_add_static_box(floor, Vector3(12.0, 0.16, 12.0))
	_box("Back Wall", Vector3(12.0, 5.5, 0.20), Vector3(0, 2.75, -1.72), Color(0.79, 0.82, 0.78))
	for bracket_x in [-0.90, 0.90]:
		var bracket := _box("Whiteboard Wall Bracket", Vector3(0.10, 0.13, 0.16), Vector3(bracket_x, 2.35, -1.55), Color(0.18, 0.22, 0.26), 0.78, 0.24)
		add_child(bracket)
	_box("Left Wall", Vector3(0.16, 5.5, 12.0), Vector3(-6.0, 2.75, 3.2), Color(0.70, 0.75, 0.76))
	_box("Right Wall", Vector3(0.16, 5.5, 12.0), Vector3(6.0, 2.75, 3.2), Color(0.70, 0.75, 0.76))
	# A few low-detail desks and chairs establish the classroom without blocking the board.
	for x in [-3.2, -1.9, 1.9, 3.2]:
		var desk := _box("Student Desk", Vector3(0.95, 0.08, 0.58), Vector3(x, 0.78, 2.15), Color(0.49, 0.30, 0.17), 0.0, 0.55)
		add_child(desk)
		for leg_x in [-0.38, 0.38]:
			for leg_z in [-0.22, 0.22]:
				_box("Desk Leg", Vector3(0.045, 0.72, 0.045), Vector3(x + leg_x, 0.38, 2.15 + leg_z), Color(0.12, 0.15, 0.18), 0.65, 0.32)
		var chair := _box("Class Chair", Vector3(0.48, 0.06, 0.45), Vector3(x, 0.43, 2.95), Color(0.12, 0.38, 0.47), 0.1, 0.42)
		add_child(chair)
		var chair_back := _box("Chair Back", Vector3(0.48, 0.42, 0.055), Vector3(x, 0.66, 3.15), Color(0.12, 0.38, 0.47), 0.1, 0.42)
		add_child(chair_back)
	# Classroom identity sign and simple ceiling lights make the wider view feel intentional.
	_box("Classroom Sign", Vector3(2.4, 0.42, 0.07), Vector3(-3.9, 4.55, -1.58), Color(0.06, 0.18, 0.25), 0.25, 0.32)
	var sign := Label3D.new()
	sign.text = "SCIENCE   /   ROOM 204"
	sign.font_size = 52
	sign.pixel_size = 0.0024
	sign.modulate = Color(0.40, 1.0, 0.88)
	sign.position = Vector3(-3.9, 4.55, -1.53)
	add_child(sign)
	# The scene's shared key and fill lights illuminate the room; avoid adding duplicates here.

func _build_wall_board() -> void:
	board_root = Node3D.new()
	board_root.name = "Wall Mounted Whiteboard Assembly"
	board_root.position = BOARD_CENTER
	board_root.rotation.x = PI / 2.0 # local board X/Z becomes world X/Y, front points into room (+Z)
	add_child(board_root)
	var stage := _box("Whiteboard Backing", Vector3(BOARD_SIZE.x + 0.14, 0.07, BOARD_SIZE.y + 0.14), Vector3(0, -0.06, 0), Color(0.10, 0.14, 0.19), 0.65, 0.25)
	board_root.add_child(stage)
	var board := _box("Whiteboard Surface", Vector3(BOARD_SIZE.x, 0.025, BOARD_SIZE.y), Vector3(0, 0, 0), Color(0.96, 0.97, 0.93), 0.0, 0.22)
	board_root.add_child(board)
	var frame_mat := StandardMaterial3D.new()
	frame_mat.albedo_color = Color(0.11, 0.17, 0.23)
	frame_mat.metallic = 0.72
	frame_mat.roughness = 0.23
	# Horizontal rails run across X; vertical rails run along local Z. Keep their axes and positions distinct.
	for side in 2:
		var rail := MeshInstance3D.new()
		rail.name = "Whiteboard Horizontal Frame %d" % side
		var rail_mesh := BoxMesh.new()
		rail_mesh.size = Vector3(BOARD_SIZE.x + 0.08, 0.045, 0.04)
		rail.mesh = rail_mesh
		rail.position = Vector3(0, 0.008, (-1.0 if side == 0 else 1.0) * (BOARD_SIZE.y / 2.0 + 0.025))
		rail.material_override = frame_mat
		board_root.add_child(rail)
	for side in 2:
		var rail := MeshInstance3D.new()
		rail.name = "Whiteboard Vertical Frame %d" % side
		var rail_mesh := BoxMesh.new()
		rail_mesh.size = Vector3(0.04, 0.045, BOARD_SIZE.y)
		rail.mesh = rail_mesh
		rail.position = Vector3((-1.0 if side == 0 else 1.0) * (BOARD_SIZE.x / 2.0 + 0.025), 0.008, 0)
		rail.material_override = frame_mat
		board_root.add_child(rail)
	var back_body := StaticBody3D.new()
	back_body.name = "Board Collision"
	back_body.position = Vector3(0, 0, 0)
	board_root.add_child(back_body)
	var collision := CollisionShape3D.new()
	var collision_shape := BoxShape3D.new()
	collision_shape.size = Vector3(BOARD_SIZE.x, 0.025, BOARD_SIZE.y)
	collision.shape = collision_shape
	back_body.add_child(collision)
	_build_lorem_text()

func _build_lorem_text() -> void:
	var font := SystemFont.new()
	font.font_names = PackedStringArray(["DejaVu Sans", "Arial"])
	const FONT_SIZE := 48
	const PIXEL_SIZE := 0.00065
	const LEFT_EDGE := -1.08
	const RIGHT_EDGE := 1.08
	const DOCK_CLEAR_EDGE := 0.67
	const ROW_COUNT := 15
	const ROW_PITCH := 0.108
	var lorem := "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur. Excepteur sint occaecat cupidatat non proident, sunt in culpa qui officia deserunt mollit anim id est laborum. "
	var words := PackedStringArray()
	for repeat in 5:
		words.append_array(lorem.split(" ", false))
	var word_cursor := 0
	var word_index := 0
	for row in ROW_COUNT:
		var z := -0.79 + float(row) * ROW_PITCH
		var row_right := DOCK_CLEAR_EDGE if z > 0.43 else RIGHT_EDGE
		var x := LEFT_EDGE
		while word_cursor < words.size():
			var word: String = words[word_cursor]
			var word_width := font.get_string_size(word, HORIZONTAL_ALIGNMENT_LEFT, -1, FONT_SIZE).x * PIXEL_SIZE
			if x + word_width > row_right:
				break
			var label := Label3D.new()
			label.name = "BoardWord_%03d" % word_index
			label.text = word
			label.font = font
			label.font_size = FONT_SIZE
			label.pixel_size = PIXEL_SIZE
			label.modulate = Color(0.035, 0.10, 0.19)
			label.position = Vector3(x, 0.014, z)
			label.rotation.x = -PI / 2.0
			board_root.add_child(label)
			erased_words.append(label)
			var space_width := font.get_string_size(" ", HORIZONTAL_ALIGNMENT_LEFT, -1, FONT_SIZE).x * PIXEL_SIZE * 0.7
			x += word_width + space_width
			word_cursor += 1
			word_index += 1

func _build_dock() -> void:
	# The robot faces inward from the corner. Its pins extend along +board-Z at this heading.
	# The charger face sits on the inward edge; its body reaches the board's outer corner.
	var face_z := DOCK_POSITION.z + POGO_TIP_FORWARD
	var dock := _box("Pogo Pin Charging Station", Vector3(0.19, 0.050, 0.13),
		Vector3(DOCK_POSITION.x, 0.039, face_z + 0.065), Color(0.055, 0.12, 0.16), 0.55, 0.28)
	dock_material = StandardMaterial3D.new()
	dock_material.albedo_color = Color(0.08, 0.52, 0.32)
	dock_material.emission_enabled = true
	dock_material.emission = Color(0.02, 0.24, 0.12)
	dock.material_override = dock_material
	board_root.add_child(dock)
	for side in [-1.0, 1.0]:
		var guide := _box("Dock Nose Guide", Vector3(0.012, 0.046, 0.13),
			Vector3(DOCK_POSITION.x + side * 0.095, 0.044, face_z + 0.065), Color(0.10, 0.26, 0.31), 0.65, 0.25)
		board_root.add_child(guide)
	for side in [-1.0, 1.0]:
		var contact := _box("Dock Copper Contact %s" % ("L" if side < 0 else "R"),
			Vector3(0.012, 0.018, 0.004),
			Vector3(DOCK_POSITION.x + side * POGO_LATERAL_SPACING / 2.0, DOCK_POSITION.y + 0.0095, face_z + 0.002),
			Color(0.96, 0.57, 0.16), 0.86, 0.20)
		board_root.add_child(contact)
	var label := Label3D.new()
	label.name = "Dock Label"
	label.text = "HOME  /  POGO CHARGE"
	label.font_size = 38
	label.pixel_size = 0.00048
	label.modulate = Color(0.02, 0.24, 0.11)
	label.position = Vector3(DOCK_POSITION.x, 0.015, face_z - 0.15)
	label.rotation.x = -PI / 2.0
	board_root.add_child(label)
	dock_light = OmniLight3D.new()
	dock_light.name = "Dock Status Light"
	dock_light.position = BOARD_CENTER + board_root.basis * Vector3(DOCK_POSITION.x, 0.09, face_z + 0.065)
	dock_light.light_color = Color(0.1, 1.0, 0.45)
	dock_light.light_energy = 0.4
	dock_light.omni_range = 0.55
	add_child(dock_light)

func _build_camera() -> void:
	camera = Camera3D.new()
	camera.name = "Classroom Demo Camera"
	camera.position = Vector3(0, 3.8, 3.6)
	camera.fov = 36.0
	camera.current = true
	add_child(camera)
	camera.look_at(Vector3(0, 2.25, -1.45), Vector3.UP)

func _build_hud() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	var panel := PanelContainer.new()
	panel.position = Vector2(22, 20)
	panel.custom_minimum_size = Vector2(420, 188)
	var panel_style := StyleBoxFlat.new()
	panel_style.bg_color = Color(0.025, 0.045, 0.075, 0.96)
	panel_style.border_color = Color(0.13, 0.86, 0.79)
	panel_style.set_border_width_all(2)
	panel_style.set_corner_radius_all(12)
	panel_style.content_margin_left = 16
	panel_style.content_margin_right = 16
	panel_style.content_margin_top = 12
	panel_style.content_margin_bottom = 12
	panel.add_theme_stylebox_override("panel", panel_style)
	layer.add_child(panel)
	var column := VBoxContainer.new()
	column.add_theme_constant_override("separation", 7)
	panel.add_child(column)
	var title := Label.new()
	title.text = "ROOM 204   /   WHITEBOARD RUN"
	title.add_theme_color_override("font_color", Color(0.28, 1.0, 0.86))
	title.add_theme_font_size_override("font_size", 19)
	column.add_child(title)
	status_label = Label.new()
	status_label.add_theme_color_override("font_color", Color(0.92, 0.96, 1.0))
	status_label.add_theme_font_size_override("font_size", 15)
	column.add_child(status_label)
	battery_label = Label.new()
	battery_label.add_theme_color_override("font_color", Color(1.0, 0.78, 0.30))
	battery_label.add_theme_font_size_override("font_size", 14)
	column.add_child(battery_label)
	battery_bar = _make_bar(Color(0.22, 0.92, 0.51))
	column.add_child(battery_bar)
	clean_label = Label.new()
	clean_label.add_theme_color_override("font_color", Color(0.45, 0.84, 0.98))
	clean_label.add_theme_font_size_override("font_size", 13)
	column.add_child(clean_label)
	clean_bar = _make_bar(Color(0.14, 0.82, 0.92))
	column.add_child(clean_bar)
	var controls := Label.new()
	controls.text = "W/S drive   A/D steer   HOME park + charge   F10 low power   R reset"
	controls.add_theme_color_override("font_color", Color(0.70, 0.77, 0.88))
	controls.add_theme_font_size_override("font_size", 12)
	column.add_child(controls)

func _make_bar(color: Color) -> ProgressBar:
	var bar := ProgressBar.new()
	bar.custom_minimum_size = Vector2(380, 13)
	bar.max_value = 100.0
	bar.show_percentage = false
	var fill := StyleBoxFlat.new()
	fill.bg_color = color
	fill.set_corner_radius_all(6)
	bar.add_theme_stylebox_override("fill", fill)
	var background := StyleBoxFlat.new()
	background.bg_color = Color(0.12, 0.16, 0.21)
	background.set_corner_radius_all(6)
	bar.add_theme_stylebox_override("background", background)
	return bar

func _unhandled_input(event: InputEvent) -> void:
	if not (event is InputEventKey) or not event.pressed or event.echo:
		return
	if event.keycode == KEY_HOME and not fallen:
		returning_to_dock = true
		parking_phase = 0
	if event.keycode == KEY_R:
		get_tree().reload_current_scene()
	if event.keycode == KEY_F10:
		_set_low_performance_mode(not low_performance_mode)
	if event.keycode == KEY_F11:
		var mode := DisplayServer.window_get_mode()
		DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_WINDOWED if mode == DisplayServer.WINDOW_MODE_FULLSCREEN else DisplayServer.WINDOW_MODE_FULLSCREEN)

func _physics_process(delta: float) -> void:
	elapsed += delta
	if fallen:
		_update_fall(delta)
	elif returning_to_dock:
		_update_return_drive(delta)
		if returning_to_dock and battery_seconds <= 0.0:
			_start_fall()
	else:
		_update_player_drive(delta)
		battery_seconds = maxf(0.0, battery_seconds - delta)
		if battery_seconds <= 0.0:
			_start_fall()
	ui_refresh_elapsed += delta
	if ui_refresh_elapsed >= UI_REFRESH_INTERVAL:
		var refresh_delta := ui_refresh_elapsed
		ui_refresh_elapsed = 0.0
		_update_cleaning()
		_update_hud(refresh_delta)

func _optimize_robot_shadows() -> void:
	# Tiny fasteners, sensors, and board electronics add many shadow draw calls but
	# do not change the robot's silhouette. Keep shadows on the larger visible parts.
	var pending: Array[Node] = [robot]
	while not pending.is_empty():
		var parent: Node = pending.pop_back()
		for child in parent.get_children():
			pending.append(child)
			if child is MeshInstance3D and child.mesh != null:
				var bounds: Vector3 = child.mesh.get_aabb().size * child.scale
				if maxf(bounds.x, maxf(bounds.y, bounds.z)) < 0.015:
					child.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF
				else:
					robot_shadow_casters.append(child)

func _set_low_performance_mode(enabled: bool) -> void:
	low_performance_mode = enabled
	Engine.max_fps = 30 if enabled else 60
	if key_light != null:
		key_light.shadow_enabled = not enabled
	for mesh_instance in robot_shadow_casters:
		if is_instance_valid(mesh_instance):
			mesh_instance.cast_shadow = GeometryInstance3D.SHADOW_CASTING_SETTING_OFF if enabled else GeometryInstance3D.SHADOW_CASTING_SETTING_ON

func _update_player_drive(delta: float) -> void:
	var throttle := float(Input.is_physical_key_pressed(KEY_W)) - float(Input.is_physical_key_pressed(KEY_S))
	var steering := float(Input.is_physical_key_pressed(KEY_D)) - float(Input.is_physical_key_pressed(KEY_A))
	if absf(throttle) > 0.0:
		robot.rotation.y -= steering * TURN_SPEED * delta * signf(throttle)
		robot.position += -robot.basis.z * throttle * DRIVE_SPEED * delta
		robot.position.x = clampf(robot.position.x, -BOARD_SIZE.x / 2.0 + 0.09, BOARD_SIZE.x / 2.0 - 0.09)
		robot.position.z = clampf(robot.position.z, -BOARD_SIZE.y / 2.0 + 0.09, BOARD_SIZE.y / 2.0 - 0.09)

func _update_return_drive(delta: float) -> void:
	var y := robot.position.y
	var approach := Vector3(DOCK_POSITION.x - 0.22, y, DOCK_POSITION.z - 0.16)
	var align := Vector3(DOCK_POSITION.x, y, DOCK_POSITION.z - 0.16)
	match parking_phase:
		0:
			if _drive_toward(approach, delta):
				parking_phase = 1
		1:
			if _drive_toward(align, delta):
				parking_phase = 2
		2:
			_rotate_robot_toward(DOCK_HEADING, delta) # point the front pogo pins into the charger face
			if absf(wrapf(robot.rotation.y - DOCK_HEADING, -PI, PI)) < 0.035:
				parking_phase = 3
		3:
			if _drive_toward(DOCK_POSITION, delta):
				robot.position = DOCK_POSITION
				robot.rotation.y = DOCK_HEADING
				returning_to_dock = false
				charging = true
	if not returning_to_dock:
		battery_seconds = minf(BATTERY_SECONDS, battery_seconds + delta * 0.8)
	else:
		battery_seconds = maxf(0.0, battery_seconds - delta)

func _drive_toward(target: Vector3, delta: float) -> bool:
	var offset := target - robot.position
	offset.y = 0.0
	if offset.length() < 0.025:
		return true
	var desired_yaw := atan2(-offset.x, -offset.z)
	_rotate_robot_toward(desired_yaw, delta)
	if absf(wrapf(desired_yaw - robot.rotation.y, -PI, PI)) < 0.18:
		robot.position += -robot.basis.z * minf(DRIVE_SPEED * delta, offset.length())
	return false

func _rotate_robot_toward(target_yaw: float, delta: float) -> void:
	var angle_left := wrapf(target_yaw - robot.rotation.y, -PI, PI)
	robot.rotation.y += clampf(angle_left, -TURN_SPEED * delta, TURN_SPEED * delta)

func _start_fall() -> void:
	fallen = true
	returning_to_dock = false
	charging = false
	robot.reparent(self, true)
	fall_velocity = Vector3(0.0, -0.15, 0.0)

func _update_fall(delta: float) -> void:
	fall_velocity.y -= 9.8 * delta
	robot.global_position += fall_velocity * delta
	robot.rotate_object_local(Vector3(1, 0, 0), delta * 0.8)
	# The classroom floor top is -0.02 m; the robot root is at its wheel contact plane.
	if robot.global_position.y <= -0.018:
		robot.global_position.y = -0.018
		fall_velocity = Vector3.ZERO
		status_label.text = "BATTERY EMPTY   /   ROBOT LANDED ON CLASSROOM FLOOR"

func _update_cleaning() -> void:
	if fallen:
		return
	for word in erased_words:
		if not is_instance_valid(word) or not word.visible:
			continue
		var local := robot.to_local(word.global_position)
		if absf(local.x) < 0.064 and absf(local.z) < 0.067:
			word.visible = false

func _update_hud(delta: float) -> void:
	var docked := charging and not returning_to_dock and _pogo_contacts_mated()
	if docked and battery_seconds < BATTERY_SECONDS:
		battery_seconds = minf(BATTERY_SECONDS, battery_seconds + delta * 16.0)
	if not fallen:
		if returning_to_dock:
			status_label.text = "AUTOPILOT   /   LINE UP, TURN, PIN-DOCK"
		elif docked and battery_seconds >= BATTERY_SECONDS:
			status_label.text = "DOCKED   /   CHARGE COMPLETE"
		elif docked:
			status_label.text = "DOCKED   /   CHARGING"
		else:
			status_label.text = "DRIVE OVER THE WRITING TO ERASE IT"
	var charge_percent := 100.0 * battery_seconds / BATTERY_SECONDS
	battery_label.text = "BATTERY   %02d%%    %02d:%02d" % [int(charge_percent), int(int(battery_seconds) / 60), int(battery_seconds) % 60]
	battery_bar.value = charge_percent
	var cleaned := 100.0 * float(_count_erased()) / float(erased_words.size())
	clean_label.text = "BOARD CLEANED   %02d%%" % int(cleaned)
	clean_bar.value = cleaned
	if dock_material != null:
		var pulse := 0.5 + 0.5 * sin(elapsed * 3.8)
		dock_material.emission_energy_multiplier = 0.28 + pulse * (1.1 if docked else 0.25)
		dock_light.light_energy = 0.4 + pulse * (1.5 if docked else 0.25)

func _pogo_contacts_mated() -> bool:
	var face_z := DOCK_POSITION.z + POGO_TIP_FORWARD
	for side in [-1.0, 1.0]:
		# A 180° heading swaps the left/right pin positions in board-local X.
		var pin_tip := robot.to_global(Vector3(-side * POGO_LATERAL_SPACING / 2.0, 0.0095, -POGO_TIP_FORWARD))
		var pad_face := board_root.to_global(Vector3(DOCK_POSITION.x + side * POGO_LATERAL_SPACING / 2.0, DOCK_POSITION.y + 0.0095, face_z))
		if pin_tip.distance_to(pad_face) > 0.004:
			return false
	return true

func _count_erased() -> int:
	var count := 0
	for word in erased_words:
		if is_instance_valid(word) and not word.visible:
			count += 1
	return count

func _box(object_name: String, size: Vector3, position: Vector3, color: Color, metallic := 0.0, roughness := 0.55) -> MeshInstance3D:
	var mesh_instance := MeshInstance3D.new()
	mesh_instance.name = object_name
	var box_mesh := BoxMesh.new()
	box_mesh.size = size
	mesh_instance.mesh = box_mesh
	mesh_instance.position = position
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.metallic = metallic
	material.roughness = roughness
	mesh_instance.material_override = material
	return mesh_instance

func _add_static_box(mesh: MeshInstance3D, size: Vector3) -> void:
	var body := StaticBody3D.new()
	body.name = "%s Collision" % mesh.name
	body.position = mesh.position
	add_child(body)
	var collision := CollisionShape3D.new()
	var box_shape := BoxShape3D.new()
	box_shape.size = size
	collision.shape = box_shape
	body.add_child(collision)
	add_child(mesh)
