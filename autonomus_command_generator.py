import tkinter as tk
from tkinter import messagebox
from PIL import Image, ImageTk
import math
import random

# Field and game element constants
TILE_SIZE_MM = 600  # Each tile is 600mm x 600mm
FIELD_SIZE_MM = TILE_SIZE_MM * 6  # Field is 6x6 tiles
FIELD_SIZE_PX = FIELD_SIZE_MM // 10  # Scale down for display
WAYPOINT_RADIUS = 5  # Radius for waypoints
CENTRAL_LINE_OFFSET = 10  # Offset from central line to avoid touching

# Command types and colors
COMMANDS = {
    'Pick Up': 'red',
    'Place': 'green',
    'Scoop': 'purple',
    'Release': 'orange',
    'Clasp': 'yellow',
    'None': 'blue',
}

class MainApp:
    def __init__(self, master):
        self.master = master
        self.master.title("Robot Path Planning App")

        # Create the input fields for robot dimensions and place them above the map
        self.create_input_fields()

        # Initialize the field canvas
        self.field_canvas = None  # Initialize later when starting the field

    def create_input_fields(self):
        """Creates input fields for robot dimensions directly above the map."""
        self.input_frame = tk.Frame(self.master)
        self.input_frame.pack(side=tk.TOP, pady=10)

        # Robot dimensions entry fields
        tk.Label(self.input_frame, text="Robot Width (mm):").grid(row=0, column=0, padx=5)
        self.width_entry = tk.Entry(self.input_frame, width=10)
        self.width_entry.grid(row=0, column=1)

        tk.Label(self.input_frame, text="Robot Height (mm):").grid(row=0, column=2, padx=5)
        self.height_entry = tk.Entry(self.input_frame, width=10)
        self.height_entry.grid(row=0, column=3)

        tk.Label(self.input_frame, text="Robot Weight (kg):").grid(row=0, column=4, padx=5)
        self.weight_entry = tk.Entry(self.input_frame, width=10)
        self.weight_entry.grid(row=0, column=5)

        # Button to generate random test data
        self.fill_random_btn = tk.Button(self.input_frame, text="Fill Random Data", command=self.fill_random_info)
        self.fill_random_btn.grid(row=0, column=6, padx=5)

        # Start button (to confirm dimensions but without changing screen)
        self.start_button = tk.Button(self.input_frame, text="Start", command=self.check_robot_info)
        self.start_button.grid(row=0, column=7, padx=5)

        # Add a button to export the path/commands to a C file
        self.export_btn = tk.Button(self.input_frame, text="Export Data", command=self.export_to_files, state=tk.DISABLED)
        self.export_btn.grid(row=0, column=8, padx=5)

        # Side selection buttons
        self.side_frame = tk.Frame(self.master)
        self.side_frame.pack(side=tk.TOP, pady=5)

        self.side_var = tk.StringVar(value="none")  # Keep track of selected side
        self.left_side_btn = tk.Radiobutton(self.side_frame, text="Left Side", variable=self.side_var, value="left", command=self.update_side)
        self.left_side_btn.pack(side=tk.LEFT)

        self.right_side_btn = tk.Radiobutton(self.side_frame, text="Right Side", variable=self.side_var, value="right", command=self.update_side)
        self.right_side_btn.pack(side=tk.LEFT)

    def fill_random_info(self):
        """Fills in random robot dimensions and weight for testing purposes."""
        random_width = random.randint(200, 500)
        random_height = random.randint(200, 500)
        random_weight = round(random.uniform(1.0, 10.0), 2)

        self.width_entry.delete(0, tk.END)
        self.width_entry.insert(0, str(random_width))

        self.height_entry.delete(0, tk.END)
        self.height_entry.insert(0, str(random_height))

        self.weight_entry.delete(0, tk.END)
        self.weight_entry.insert(0, str(random_weight))

    def check_robot_info(self):
        """Check if robot dimensions are provided before enabling the export button."""
        try:
            width = float(self.width_entry.get())
            height = float(self.height_entry.get())
            weight = float(self.weight_entry.get())
            self.start_field()  # Start the field after validating inputs
        except ValueError:
            messagebox.showerror("Input Error", "Please enter valid robot dimensions.")
            return

        # Enable the export button if dimensions are valid
        self.export_btn.config(state=tk.NORMAL)

    def start_field(self):
        # Initialize the field canvas (only once the dimensions are valid)
        if not self.field_canvas:
            self.field_canvas = FieldCanvas(self.master, self.side_var.get())

    def update_side(self):
        """Update side selection and apply restriction on path placement."""
        if self.field_canvas:
            self.field_canvas.selected_side = self.side_var.get()
            self.field_canvas.update_side_restriction()

    def export_to_files(self):
        """Export the path and commands to a C file."""
        if not self.field_canvas:
            messagebox.showerror("Error", "Field is not initialized.")
            return
        
        self.field_canvas.export_to_files()


class FieldCanvas:
    def __init__(self, master, selected_side):
        self.master = master
        self.selected_side = selected_side

        # Load the field background image
        self.field_image = Image.open("field.png")  # Replace with your image path
        self.field_image = self.field_image.resize((FIELD_SIZE_PX, FIELD_SIZE_PX), Image.LANCZOS)
        self.field_photo = ImageTk.PhotoImage(self.field_image)

        # Create the canvas for the field with fixed dimensions
        self.canvas = tk.Canvas(self.master, width=FIELD_SIZE_PX, height=FIELD_SIZE_PX)
        self.canvas.pack()

        # Set the image as the background of the canvas
        self.canvas.create_image(0, 0, anchor=tk.NW, image=self.field_photo)

        # Draw the transparent grid overlay on top of the image
        self.draw_grid()

        # Path data and game elements
        self.path_points = []
        self.dragging_curve = False  # Flag to check if we're dragging a curve control point
        self.current_curve = None  # Store the curve currently being dragged
        self.selected_waypoint_index = -1  # Index of the selected waypoint
        self.waypoint_commands = {}  # Store commands for each waypoint

        self.curve_mode = False
        self.temp_curve = None
        self.last_point = None

        # Command management
        self.pending_clasp = False  # Track if clasp is needed before scooping
        self.scoops_to_release = 0  # Track how many scoops before release is needed

        # Add mouse click binding for adding waypoints (right for straight, left for curve)
        self.canvas.bind("<Button-1>", self.start_curve_point)   # Left-click to start the curve
        self.canvas.bind("<ButtonRelease-1>", self.finalize_curve_point)  # Release to finalize curve
        self.canvas.bind("<B1-Motion>", self.adjust_curve_point)  # Drag to adjust curve control

        self.canvas.bind("<Button-3>", self.add_straight_line)  # Right-click for straight line
        self.master.bind("<Up>", lambda e: self.cycle_waypoint(1))  # Up to select next waypoint
        self.master.bind("<Down>", lambda e: self.cycle_waypoint(-1))  # Down to select previous waypoint

        # Side restriction
        self.central_line_x = FIELD_SIZE_PX // 2
        self.update_side_restriction()

        # Command buttons
        self.create_command_buttons()

    def update_side_restriction(self):
        """Visually update the restricted side and disallow points on the wrong side."""
        self.canvas.delete("side_restriction")

        if self.selected_side == "left":
            # Shade the right side
            self.canvas.create_rectangle(self.central_line_x, 0, FIELD_SIZE_PX, FIELD_SIZE_PX, fill="lightgrey", stipple="gray25", tags="side_restriction")
        elif self.selected_side == "right":
            # Shade the left side
            self.canvas.create_rectangle(0, 0, self.central_line_x, FIELD_SIZE_PX, fill="lightgrey", stipple="gray25", tags="side_restriction")

    def is_valid_point(self, x):
        """Check if the point is on the valid side based on the central line."""
        if self.selected_side == "left" and x > self.central_line_x - CENTRAL_LINE_OFFSET:
            messagebox.showerror("Invalid Point", "You cannot place waypoints on the right side.")
            return False
        if self.selected_side == "right" and x < self.central_line_x + CENTRAL_LINE_OFFSET:
            messagebox.showerror("Invalid Point", "You cannot place waypoints on the left side.")
            return False
        return True

    def draw_grid(self):
        """Draw a 6x6 transparent grid on top of the field for reference (transparent overlay effect)."""
        for i in range(6):
            for j in range(6):
                x0 = i * TILE_SIZE_MM // 10  # Convert mm to pixels
                y0 = j * TILE_SIZE_MM // 10
                x1 = x0 + TILE_SIZE_MM // 10
                y1 = y0 + TILE_SIZE_MM // 10
                self.canvas.create_rectangle(x0, y0, x1, y1, outline="black", width=1, stipple="gray50")

    def add_straight_line(self, event):
        """Adds straight-line waypoints for the robot path on right-click."""
        x, y = event.x, event.y

        if not self.is_valid_point(x):
            return  # Don't allow invalid points

        if not self.path_points:
            # First point is just the starting point, no lines are drawn
            self.add_starting_point(x, y)
            return

        self.path_points.append((x, y))
        self.waypoint_commands[(x, y)] = 'None'  # Initialize command for new waypoint
        self.canvas.create_oval(x - 5, y - 5, x + 5, y + 5, fill="blue")
        print(f"Waypoint added (straight line): {x}, {y}")

        # If more than one point exists, draw straight lines between them
        if len(self.path_points) > 1:
            self.draw_line_with_arrow(self.path_points[-2], self.path_points[-1])

    def start_curve_point(self, event):
        """Start the curve by setting an initial point and allowing user to drag."""
        x, y = event.x, event.y

        if not self.is_valid_point(x):
            return  # Don't allow invalid points

        if not self.path_points:
            # First point is just the starting point, no curves are drawn
            self.add_starting_point(x, y)
            return

        self.path_points.append((x, y))  # Initial point
        self.waypoint_commands[(x, y)] = 'None'  # Initialize command for new waypoint
        self.dragging_curve = True
        print(f"Curve start point: {x}, {y}")

    def adjust_curve_point(self, event):
        """Adjust the control point for the curve by dragging the mouse."""
        if not self.dragging_curve:
            return

        # Clear the previous curve to redraw dynamically
        if self.current_curve:
            self.canvas.delete(self.current_curve)

        # Create the quadratic Bezier curve based on control point adjustment
        control_x, control_y = event.x, event.y
        p1 = self.path_points[-2]  # Starting point of curve
        p2 = self.path_points[-1]  # Intermediate point
        self.current_curve = self.draw_bezier_curve(p1, p2, (control_x, control_y))

        print(f"Adjusting curve to control point: {control_x, control_y}")

    def finalize_curve_point(self, event):
        """Finalize the curve by ending the drag and making the curve permanent."""
        if not self.dragging_curve:
            return

        # Finalize the curve and add the last point as a permanent waypoint
        self.dragging_curve = False
        control_x, control_y = event.x, event.y
        last_curve_end = self.calculate_bezier_end(self.path_points[-2], self.path_points[-1], (control_x, control_y))

        # Make the final curve permanent by creating it again
        p1 = self.path_points[-2]  # Starting point
        p2 = last_curve_end  # Actual end of the curve
        self.draw_bezier_curve(p1, p2, (control_x, control_y))

        # Update the last waypoint to the end of the curve
        self.path_points[-1] = p2
        self.canvas.create_oval(p2[0] - 5, p2[1] - 5, p2[0] + 5, p2[1] + 5, fill="blue")
        print(f"Curve finalized at: {p2}")

    def add_starting_point(self, x, y):
        """Add the very first point as the starting point."""
        self.path_points.append((x, y))
        self.waypoint_commands[(x, y)] = 'None'  # Initialize command for starting point
        self.canvas.create_oval(x - 5, y - 5, x + 5, y + 5, fill="orange")
        self.canvas.create_text(x, y - 10, text="Start", fill="orange", font=("Arial", 10))
        print(f"Starting point added: {x}, {y}")

    def draw_line_with_arrow(self, point1, point2):
        """Draws a line between two points with an arrow indicating direction."""
        x1, y1 = point1
        x2, y2 = point2
        self.canvas.create_line(x1, y1, x2, y2, arrow=tk.LAST)

    def draw_bezier_curve(self, p1, p2, control):
        """Draw and return a quadratic Bezier curve."""
        points = self.calculate_quadratic_bezier_points(p1, p2, control)
        return self.canvas.create_line(points, fill="green", smooth=True, width=2)

    def calculate_quadratic_bezier_points(self, p1, p2, control):
        """Calculate points along a quadratic Bezier curve for smooth drawing."""
        points = []
        for t in range(101):  # t from 0 to 1 in steps
            t = t / 100  # Normalize t
            x = (1 - t) ** 2 * p1[0] + 2 * (1 - t) * t * control[0] + t ** 2 * p2[0]
            y = (1 - t) ** 2 * p1[1] + 2 * (1 - t) * t * control[1] + t ** 2 * p2[1]
            points.append((x, y))
        return points

    def calculate_bezier_end(self, p1, p2, control):
        """Calculate the end point of a quadratic Bezier curve."""
        return (p2[0], p2[1])  # The end is where the curve finishes

    def cycle_waypoint(self, direction):
        """Cycle through waypoints with arrow keys."""
        if not self.path_points:
            return

        # Deselect current waypoint by reverting its color
        if self.selected_waypoint_index != -1:
            current_wp = self.path_points[self.selected_waypoint_index]
            self.update_waypoint_color(current_wp, self.waypoint_commands[current_wp])

        # Move the selection index based on the direction (-1 for up, +1 for down)
        self.selected_waypoint_index = (self.selected_waypoint_index + direction) % len(self.path_points)

        # Highlight the newly selected waypoint
        selected_wp = self.path_points[self.selected_waypoint_index]
        self.canvas.create_oval(selected_wp[0] - WAYPOINT_RADIUS, selected_wp[1] - WAYPOINT_RADIUS,
                                selected_wp[0] + WAYPOINT_RADIUS, selected_wp[1] + WAYPOINT_RADIUS,
                                outline="yellow", width=2)
        print(f"Waypoint selected at: {selected_wp}")

    def create_command_buttons(self):
        """Create buttons for assigning commands to waypoints."""
        pick_up_btn = tk.Button(self.master, text="Pick Up", bg="red", command=lambda: self.assign_command('Pick Up'))
        pick_up_btn.pack(side=tk.LEFT)

        place_btn = tk.Button(self.master, text="Place", bg="green", command=lambda: self.assign_command('Place'))
        place_btn.pack(side=tk.LEFT)

        scoop_btn = tk.Button(self.master, text="Scoop", bg="purple", command=lambda: self.assign_command('Scoop'))
        scoop_btn.pack(side=tk.LEFT)

        release_btn = tk.Button(self.master, text="Release", bg="orange", command=lambda: self.assign_command('Release'))
        release_btn.pack(side=tk.LEFT)

        clasp_btn = tk.Button(self.master, text="Clasp", bg="yellow", command=lambda: self.assign_command('Clasp'))
        clasp_btn.pack(side=tk.LEFT)

        remove_command_btn = tk.Button(self.master, text="Remove Command", command=self.remove_command)
        remove_command_btn.pack(side=tk.LEFT)

    def assign_command(self, command):
        """Assign a command to the currently selected waypoint."""
        if self.selected_waypoint_index == -1:
            messagebox.showerror("No Waypoint Selected", "Please select a waypoint first.")
            return
        selected_wp = self.path_points[self.selected_waypoint_index]

        # Validate clasp and scoop sequence
        if command == 'Scoop' and not self.pending_clasp:
            messagebox.showerror("Clasp Required", "You must clasp before scooping.")
            return
        if command == 'Scoop':
            self.scoops_to_release += 1

        if command == 'Clasp':
            self.pending_clasp = True

        if command == 'Release' and self.scoops_to_release == 0:
            messagebox.showerror("No Scoops", "You cannot release without scooping first.")
            return
        if command == 'Release':
            self.scoops_to_release = 0  # Reset scoop count after release
            self.pending_clasp = False

        self.waypoint_commands[selected_wp] = command
        self.update_waypoint_color(selected_wp, command)
        print(f"Command '{command}' assigned to {selected_wp}")

    def remove_command(self):
        """Remove the command from the currently selected waypoint."""
        if self.selected_waypoint_index == -1:
            messagebox.showerror("No Waypoint Selected", "Please select a waypoint first.")
            return
        selected_wp = self.path_points[self.selected_waypoint_index]
        self.waypoint_commands[selected_wp] = 'None'  # Reset the command to 'None'
        self.update_waypoint_color(selected_wp, 'None')
        print(f"Command removed from {selected_wp}")

    def update_waypoint_color(self, waypoint, command):
        """Update the color of a waypoint based on the assigned command."""
        wx, wy = waypoint
        self.canvas.create_oval(wx - WAYPOINT_RADIUS, wy - WAYPOINT_RADIUS, wx + WAYPOINT_RADIUS, wy + WAYPOINT_RADIUS, fill=COMMANDS[command])

    def calculate_distance(self, p1, p2):
        """Calculate Euclidean distance between two points."""
        return math.sqrt((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2)

    def calculate_dynamic_speed(self, distance):
        """Determine the speed dynamically based on the distance."""
        base_speed = 40  # Base speed
        max_speed = 100  # Maximum speed

        # The farther the distance, the closer to max speed we move.
        speed = base_speed + (distance / 100) * (max_speed - base_speed)
        return min(speed, max_speed)

    def generate_intermediate_points(self, p1, p2, control=None, distance_threshold=3):
        """Generate very dense intermediate points along a straight line or a Bezier curve for maximum precision."""
        points = []
        
        if control is None:
            # Straight line case
            distance = self.calculate_distance(p1, p2)
            num_points = max(1, int(distance / distance_threshold))
            
            for i in range(1, num_points + 1):
                t = i / num_points
                x = p1[0] + t * (p2[0] - p1[0])
                y = p1[1] + t * (p2[1] - p1[1])
                points.append((x, y))
        else:
            # Bezier curve case with very dense points
            bezier_points = self.calculate_quadratic_bezier_points(p1, p2, control)
            for i in range(1, len(bezier_points)):
                distance = self.calculate_distance(bezier_points[i - 1], bezier_points[i])
                if distance >= distance_threshold:
                    points.append(bezier_points[i])
        
        return points

    def calculate_heading(self, p1, p2):
        """Calculate the heading (angle) between two points."""
        dx = p2[0] - p1[0]
        dy = p2[1] - p1[1]
        return math.degrees(math.atan2(dy, dx))

    import math

    def export_to_files(self, c_filename="autonomous_commands.cpp", txt_filename="autonomous_commands.txt"):
        """Export the path and commands to both a C and a TXT file."""
        
        # Export to C file
        with open(c_filename, "w") as f:
            # Write header for C file
            f.write('#include <stddef.h>\n\n')

            # Enum and struct definitions
            f.write('typedef enum {\n')
            f.write('    CMD_MOVE_WITH_HEADING,\n')
            f.write('    CMD_PICK_UP,\n')
            f.write('    CMD_PLACE,\n')
            f.write('    CMD_SCOOP,\n')
            f.write('    CMD_RELEASE,\n')
            f.write('    CMD_CLASP\n')
            f.write('} CommandType;\n\n')

            f.write('typedef struct {\n')
            f.write('    CommandType command;\n')
            f.write('    float x;\n')
            f.write('    float y;\n')
            f.write('    float heading;\n')
            f.write('    float speed;\n')
            f.write('} Command;\n\n')

            # Define the command array
            f.write('Command autonomous_commands[] = {\n')

            # Write commands to C file
            for i in range(len(self.path_points) - 1):
                p1 = self.path_points[i]
                p2 = self.path_points[i + 1]
                command = self.waypoint_commands[p1]

                # Calculate heading
                heading = self.calculate_heading(p1, p2)

                # Generate intermediate points
                if i < len(self.path_points) - 1 and self.dragging_curve:
                    control = self.calculate_bezier_control_point(p1, p2)
                    intermediate_points = self.generate_intermediate_points(p1, p2, control)
                else:
                    intermediate_points = self.generate_intermediate_points(p1, p2)

                # Write command at p1 to file
                if command != 'None':
                    f.write(f'    {{ CMD_{command.upper().replace(" ", "_")}, {p1[0]}, {p1[1]}, {heading:.2f}, 0 }},\n')

                # Write intermediate points with move commands
                for point in intermediate_points:
                    distance = self.calculate_distance(p1, point)
                    speed = self.calculate_dynamic_speed(distance)
                    f.write(f'    {{ CMD_MOVE_WITH_HEADING, {point[0]}, {point[1]}, {heading:.2f}, {speed:.2f} }},\n')

            # Add the last point’s command
            final_point = self.path_points[-1]
            final_command = self.waypoint_commands[final_point]
            if final_command != 'None':
                f.write(f'    {{ CMD_{final_command.upper().replace(" ", "_")}, {final_point[0]}, {final_point[1]}, {heading:.2f}, 0 }},\n')

            # End array and write size calculation
            f.write('};\n')
            f.write(f'const size_t num_autonomous_commands = sizeof(autonomous_commands) / sizeof(autonomous_commands[0]);\n')

        print(f"C file exported to {c_filename}")

        # Export to TXT file
        with open(txt_filename, "w") as txt_file:
            for i in range(len(self.path_points) - 1):
                p1 = self.path_points[i]
                p2 = self.path_points[i + 1]
                command = self.waypoint_commands[p1]

                # Calculate heading
                heading = self.calculate_heading(p1, p2)

                # Generate intermediate points
                if i < len(self.path_points) - 1 and self.dragging_curve:
                    control = self.calculate_bezier_control_point(p1, p2)
                    intermediate_points = self.generate_intermediate_points(p1, p2, control)
                else:
                    intermediate_points = self.generate_intermediate_points(p1, p2)

                # Write command and point data to TXT file
                if command != 'None':
                    txt_file.write(f'{command.upper()} at ({p1[0]:.2f}, {p1[1]:.2f}) with heading {heading:.2f}\n')

                # Write intermediate points as move commands
                for point in intermediate_points:
                    distance = self.calculate_distance(p1, point)
                    speed = self.calculate_dynamic_speed(distance)
                    txt_file.write(f'MOVE to ({point[0]:.2f}, {point[1]:.2f}) at heading {heading:.2f} and speed {speed:.2f}\n')

            # Write final command if present
            final_point = self.path_points[-1]
            final_command = self.waypoint_commands[final_point]
            if final_command != 'None':
                txt_file.write(f'{final_command.upper()} at ({final_point[0]:.2f}, {final_point[1]:.2f}) with heading {heading:.2f}\n')

        print(f"TXT file exported to {txt_filename}")

# Main application loop
if __name__ == "__main__":
    root = tk.Tk()
    app = MainApp(root)
    root.mainloop()
