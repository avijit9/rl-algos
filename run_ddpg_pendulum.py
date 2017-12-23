import tensorflow as tf
import tensorflow.contrib.slim as slim
import numpy as np
import gym
from collections import deque
from policy_gradient.ddpg import Actor, Critic, OrnsteinUhlenbeckActionNoise

env = gym.make('Pendulum-v0')

sess = tf.Session()
actor_optimizer = tf.train.AdamOptimizer(learning_rate=0.001)
critic_optimizer = tf.train.AdamOptimizer(learning_rate=0.001)

observation_shape = env.observation_space.shape[0]
action_shape = env.action_space.shape[0]

ACTION_BOUNDS = [2.0]
BATCH_SIZE = 64

def actor_network(states):
  net = slim.stack(states, slim.fully_connected, [24, 24], activation_fn=tf.nn.relu, scope='stack')
  net = slim.fully_connected(net, action_shape, activation_fn=tf.nn.tanh, scope='full')
  # mult with action bounds
  net = ACTION_BOUNDS * net
  return net

def critic_network(states, actions):
  state_net = slim.stack(states, slim.fully_connected, [24], activation_fn=tf.nn.relu, scope='stack_state')
  action_net = slim.stack(actions, slim.fully_connected, [24], activation_fn=tf.nn.relu, scope='stack_action')
  net = tf.concat([state_net, action_net], 1)
  net = slim.stack(net, slim.fully_connected, [24], activation_fn=tf.nn.relu, scope='stack')
  net = slim.fully_connected(net, 1, activation_fn=tf.nn.relu, scope='full')
  net = tf.squeeze(net, [1])
  return net

actor = Actor(actor_network, actor_optimizer, sess, observation_shape, action_shape)
critic = Critic(critic_network, critic_optimizer, sess, observation_shape, action_shape)
actor_noise = OrnsteinUhlenbeckActionNoise(mu=np.zeros(action_shape))

MAX_EPISODES = 10000
MAX_STEPS    = 200

sess.run(tf.global_variables_initializer())

episode_history = deque(maxlen=100)
memory_buffer = deque(maxlen=10000)
for e in range(MAX_EPISODES):
  state = env.reset()
  cum_reward = 0
  while True:
    action = actor.predict([state])[0] + actor_noise()
    next_state, reward, done, _ = env.step(action)
    cum_reward += reward
    memory_buffer.append((state, action, reward, next_state, 0.0 if done else 1.0))

    if len(memory_buffer) > BATCH_SIZE:
      indices = np.random.choice(len(memory_buffer), BATCH_SIZE, replace=False)
      states, actions, rewards, next_states, notdones = zip(*[memory_buffer[idx] for idx in indices])

      target_actions_next_states = actor.predict_target(next_states)
      critic.train(states=states, 
        actions=actions, 
        rewards=rewards, 
        next_states=next_states, 
        target_actions_next_states=target_actions_next_states, 
        notdones=notdones)

      predicted_actions = actor.predict(states)
      action_gradients = critic.get_action_gradients(states, predicted_actions)
      actor.train(states=states, action_gradients=action_gradients)

      # update targets
      actor.update_targets()
      critic.update_targets()

    if done:
      # train agent
      # print the score and break out of the loop
      episode_history.append(cum_reward)
      print("episode: {}/{}, score: {}, avg score for 100 runs: {:.2f}".format(e, MAX_EPISODES, cum_reward, np.mean(episode_history)))
      break
    state = next_state