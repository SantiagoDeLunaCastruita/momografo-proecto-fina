CONECCION MONGO ATLAS:

mongodb+srv://Said_Ramirez:NfT1w9CGzgETVGuV@escuela.5rt7g7m.mongodb.net/?appName=Escuela


autoken:

ngrok config add-authtoken 3EXLGEPWW3aKirczcaRQUl9X6IK_82NWY7cc6HAKoQXS1vvnn

enlace:

https://corroding-dolphin-subway.ngrok-free.dev



para conectar con ngrok tenemos que:

1.- descargar ngrok desde la microsoft store o desde su pagina oficial 

https://ngrok.com/download/windows 

(a pesar de que es detectado como virus es completamente inofencivo)



2.- abrir el repositorio en visual studio code y realizar todos los prosesos nesesarios para que este mismo sea funcional por ejemplo usar "uv sync"


3.- abrir ngrok como administrador y colocar el comando de arriba para configurar el autoken
(ngrok config add-authtoken 3EXLGEPWW3aKirczcaRQUl9X6IK_82NWY7cc6HAKoQXS1vvnn)


4.-en la misma ventana de powershell en ngrok colocaremos el comando de "ngrok http 5000"


5.- ejecutar el .py "gestor de tareas" 


6.- finalmente abriremos el enlace que esta adjuntado en la parte superior de este archivo 
(https://corroding-dolphin-subway.ngrok-free.dev) lo puedes abrir pulsando "ctrl+click"


o tambien puedes ejeutar los comando directamente desd ela temrinal, ngrok ya esta instalado, despues de usar uv sync ejecutas el comando:
1.- ngrok config add-authtoken 3EXLGEPWW3aKirczcaRQUl9X6IK_82NWY7cc6HAKoQXS1vvnn

despues usa en la misma temrinal donde pusist el comando anterior:
2.- ngrok http 5000

y finalemte ejecuta el gestordetareas.py

el enlace deberia de ser: https://corroding-dolphin-subway.ngrok-free.dev











