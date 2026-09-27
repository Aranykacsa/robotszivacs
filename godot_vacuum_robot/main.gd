extends Node3D
func _ready() -> void:
	var robot := preload("res://Vacuum_Robot_Blockout.glb").instantiate()
	robot.position = Vector3(0, 0.85, 0)
	add_child(robot)
	var table := StaticBody3D.new()
	table.position = Vector3(0, 0.825, 0)
	add_child(table)
	var mesh := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = Vector3(0.6, 0.05, 0.6)
	mesh.mesh = box
	table.add_child(mesh)
	var collision := CollisionShape3D.new()
	var shape := BoxShape3D.new()
	shape.size = box.size
	collision.shape = shape
	table.add_child(collision)
	var label := Label.new()
	label.text = "WASD: move | Mouse: look | Space: jump | Esc: release mouse\nRobot shown at true scale on an inspection table."
	label.position = Vector2(16, 16)
	var ui := CanvasLayer.new()
	add_child(ui)
	ui.add_child(label)
